"""Единый OAuth-вход: Google, Яндекс, Mail.ru. Токены обновляются автоматически, при отказе подключение помечается «нужен повторный вход»."""
import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from ..config import settings
from ..models import utcnow
from ..security import constant_eq, sign

GOOGLE_BASE = "https://www.googleapis.com/auth/"

# provider -> сервис входа, нужные права и подпись в интерфейсе
PROVIDERS: dict[str, dict] = {
    "google_sheets": {"family": "google", "scopes": [GOOGLE_BASE + "spreadsheets"]},
    "google_calendar": {"family": "google", "scopes": [GOOGLE_BASE + "calendar"]},
    "google_gmail": {"family": "google", "scopes": ["https://mail.google.com/"], "mail": True},
    "yandex_mail": {"family": "yandex", "scopes": ["mail:imap_ro", "mail:smtp", "login:email"], "mail": True},
    # Яндекс Таблицы хранятся на Диске; отдельного cell-level API нет — работаем через Disk API
    "yandex_sheets": {
        "family": "yandex",
        "scopes": ["cloud_api:disk.read", "cloud_api:disk.write", "cloud_api:disk.info", "login:email"],
    },
    "mailru_mail": {"family": "mailru", "scopes": [], "mail": True},   # права берутся из настроек
}
OAUTH_PROVIDERS = set(PROVIDERS)
MAIL_PROVIDERS = {"email"} | {k for k, v in PROVIDERS.items() if v.get("mail")}

FAMILIES = {
    "google": {"auth": lambda: settings.google_auth_url, "token": lambda: settings.google_token_url,
               "id": lambda: settings.google_client_id, "secret": lambda: settings.google_client_secret, "pkce": True},
    "yandex": {"auth": lambda: "https://oauth.yandex.ru/authorize", "token": lambda: "https://oauth.yandex.ru/token",
               "id": lambda: settings.yandex_client_id, "secret": lambda: settings.yandex_client_secret, "pkce": False},
    "mailru": {"auth": lambda: "https://oauth.mail.ru/login", "token": lambda: "https://oauth.mail.ru/token",
               "id": lambda: settings.mailru_client_id, "secret": lambda: settings.mailru_client_secret, "pkce": False},
}


def _client() -> httpx.AsyncClient:   # точка подмены в тестах
    return httpx.AsyncClient(timeout=30.0)


def family_of(provider: str) -> str:
    return PROVIDERS[provider]["family"]


def is_configured(family: str) -> bool:
    return bool(FAMILIES[family]["id"]())


def scopes_for(provider: str) -> list[str]:
    if provider == "mailru_mail":
        return settings.mailru_mail_scopes.split()
    return PROVIDERS[provider]["scopes"]


# ───────── state и PKCE ─────────

def make_state(user_id: int, provider: str, name: str, reconnect_id: int | None = None) -> tuple[str, str]:
    """Подписанный state. Возвращает (state, nonce): из nonce на сервере выводится PKCE-проверочная строка, в ссылку она не попадает."""
    nonce = secrets.token_hex(16)
    payload = base64.urlsafe_b64encode(json.dumps(
        {"u": user_id, "p": provider, "n": name, "t": int(utcnow().timestamp()), "r": nonce, "c": reconnect_id}).encode()).decode()
    return f"{payload}.{sign(payload, 'oauth-state', 40)}", nonce


def read_state(state: str) -> dict:
    try:
        payload, sig = state.rsplit(".", 1)
        if not constant_eq(sig, sign(payload, "oauth-state", 40)):
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        if int(utcnow().timestamp()) - int(data["t"]) > 600:
            raise ValueError
        if data["p"] not in PROVIDERS:
            raise ValueError
        return data
    except Exception:
        raise HTTPException(400, "Invalid state")


def pkce_verifier(nonce: str) -> str:
    return sign(nonce, "pkce", 64)          # 64 hex-символа: подходит под требования RFC 7636, наружу не отдаётся


def pkce_challenge(nonce: str) -> str:
    digest = hashlib.sha256(pkce_verifier(nonce).encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


# ───────── ссылка входа ─────────

def build_auth_url(provider: str, state: str, nonce: str) -> str:
    family = family_of(provider)
    fam = FAMILIES[family]
    if not fam["id"]():
        raise HTTPException(500, detail={"code": "oauth_not_configured", "message": f"Вход через {family} не настроен на сервере (не заданы ключи приложения в .env)"})
    params = {"client_id": fam["id"](), "redirect_uri": settings.oauth_redirect(family), "response_type": "code", "state": state}
    scopes = scopes_for(provider)
    if scopes:
        params["scope"] = " ".join(scopes)
    if family == "google":
        params.update({"access_type": "offline", "prompt": "consent", "include_granted_scopes": "false"})
    if fam["pkce"]:
        params.update({"code_challenge": pkce_challenge(nonce), "code_challenge_method": "S256"})
    return f"{fam['auth']()}?{urlencode(params)}"


# ───────── обмен кода и обновление ─────────

def _normalize(family: str, data: dict, previous: dict | None = None) -> dict:
    previous = previous or {}
    out = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or previous.get("refresh_token"),
        "expires_in": int(data.get("expires_in") or previous.get("expires_in") or 3600),
        "obtained_at": datetime.now(timezone.utc).isoformat(),
        "scope": data.get("scope") or previous.get("scope") or "",
        "needs_reauth": False,
    }
    return out


async def exchange_code(provider: str, code: str, nonce: str) -> dict:
    family = family_of(provider)
    fam = FAMILIES[family]
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": settings.oauth_redirect(family), "client_id": fam["id"]()}
    auth = None
    if family == "google":
        data.update({"client_secret": fam["secret"](), "code_verifier": pkce_verifier(nonce)})
    else:
        auth = (fam["id"](), fam["secret"]())
    async with _client() as client:
        r = await client.post(fam["token"](), data=data, auth=auth)
    if r.status_code != 200 or "access_token" not in r.json():
        raise HTTPException(400, "oauth_exchange_failed")
    return _normalize(family, r.json())


async def refresh_tokens(provider: str, cfg: dict) -> dict | None:
    """Новые токены или None, если доступ отозван/истёк (тогда подключение нужно авторизовать заново)."""
    family = family_of(provider)
    fam = FAMILIES[family]
    refresh_token = cfg.get("refresh_token")
    if not refresh_token:
        return None
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": fam["id"]()}
    auth = None
    if family == "google":
        data["client_secret"] = fam["secret"]()
    else:
        auth = (fam["id"](), fam["secret"]())
    async with _client() as client:
        r = await client.post(fam["token"](), data=data, auth=auth)
    if r.status_code != 200 or "access_token" not in r.json():
        return "temporary" if r.status_code >= 500 else None   # сбой сервиса — не считаем доступ отозванным
    return _normalize(family, r.json(), cfg)


def is_expired(cfg: dict, leeway: int = 60) -> bool:
    obtained_at = cfg.get("obtained_at")
    if not obtained_at:
        return True
    try:
        obtained = datetime.fromisoformat(obtained_at)
        if obtained.tzinfo is None:
            obtained = obtained.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= obtained + timedelta(seconds=int(cfg.get("expires_in", 3600)) - leeway)
    except ValueError:
        return True


# ───────── кто вошёл, проверка прав, отзыв ─────────

async def fetch_account(provider: str, tokens: dict) -> dict:
    """Подпись подключения (почта или имя аккаунта) для интерфейса. Сбой не критичен."""
    family = family_of(provider)
    token = tokens["access_token"]
    try:
        async with _client() as client:
            if family == "google":
                r = await client.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {token}"})
                return {"email": r.json().get("email", "")} if r.status_code == 200 else {}
            if family == "yandex":
                r = await client.get("https://login.yandex.ru/info?format=json", headers={"Authorization": f"OAuth {token}"})
                body = r.json() if r.status_code == 200 else {}
                return {"email": body.get("default_email", ""), "account": body.get("login", "")}
            if family == "mailru":
                r = await client.get("https://oauth.mail.ru/userinfo", params={"access_token": token})
                body = r.json() if r.status_code == 200 else {}
                return {"email": body.get("email", "")}
    except Exception:
        return {}
    return {}


def missing_scopes(provider: str, tokens: dict) -> list[str]:
    """Google позволяет снять галочки с запрошенных прав. Если нужного права нет, подключение бесполезно."""
    if family_of(provider) != "google":
        return []
    granted = set((tokens.get("scope") or "").split())
    return [s for s in scopes_for(provider) if granted and s not in granted]


async def revoke(provider: str, cfg: dict) -> None:
    """Отзыв доступа на стороне сервиса при удалении подключения (где есть такой метод). Ошибки игнорируются."""
    if family_of(provider) != "google":
        return
    token = cfg.get("refresh_token") or cfg.get("access_token")
    if not token:
        return
    try:
        async with _client() as client:
            await client.post("https://oauth2.googleapis.com/revoke", data={"token": token})
    except Exception:
        pass
