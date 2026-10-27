import base64
import json
import re
from typing import Optional
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Connection, User, utcnow
from ..schemas import ConnectionCreate
from ..security import constant_eq, encrypt_config, mask_config, sign
from ..services import telegram_service
from ..services.ssrf import assert_public_url

router = APIRouter(tags=["connections"])

MAX_CONNECTIONS_PER_USER = 30
PROVIDERS = {
    "huggingface": "ai_api", "openai_compatible": "ai_api", "telegram_bot": "tool",
    "google_sheets": "tool", "google_calendar": "tool",
}
GOOGLE_SCOPES = {
    "google_sheets": "https://www.googleapis.com/auth/spreadsheets",
    "google_calendar": "https://www.googleapis.com/auth/calendar",
}
BOT_TOKEN_RE = re.compile(r"^\d{3,}:[A-Za-z0-9_-]{20,}$")


def _dto(c: Connection) -> dict:
    return {"id": c.id, "category": c.category, "provider": c.provider, "name": c.name,
            "config": mask_config({k: v for k, v in (c.config or {}).items() if k != "webhook_registered"}),
            "created_at": c.created_at}


@router.get("/connections")
async def list_connections(category: Optional[str] = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Connection).where(Connection.user_id == user.id).order_by(Connection.id)
    if category:
        query = query.where(Connection.category == category)
    rows = (await db.execute(query)).scalars().all()
    return [_dto(c) for c in rows]


@router.post("/connections")
async def create_connection(data: ConnectionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if data.provider not in PROVIDERS or PROVIDERS[data.provider] != data.category:
        raise HTTPException(400, detail={"code": "bad_provider", "message": "Неизвестный тип подключения"})
    if data.provider in GOOGLE_SCOPES:
        raise HTTPException(400, detail={"code": "use_oauth", "message": "Google-подключения создаются через вход в Google"})
    count = (await db.execute(select(func.count()).select_from(Connection).where(Connection.user_id == user.id))).scalar_one()
    if count >= MAX_CONNECTIONS_PER_USER:
        raise HTTPException(400, detail={"code": "too_many_connections", "message": f"Максимум {MAX_CONNECTIONS_PER_USER} подключений"})

    config = dict(data.config)
    if data.provider == "telegram_bot" and not BOT_TOKEN_RE.match(str(config.get("bot_token", ""))):
        raise HTTPException(400, detail={"code": "bad_bot_token", "message": "Неверный формат токена бота (ожидается 123456:ABC...)"})
    if data.provider == "openai_compatible" and config.get("base_url"):
        try:
            await assert_public_url(str(config["base_url"]))
        except ValueError as e:
            raise HTTPException(400, detail={"code": "bad_url", "message": str(e)})

    conn = Connection(user_id=user.id, category=data.category, provider=data.provider, name=data.name.strip(),
                      config=encrypt_config(config))
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _dto(conn)


@router.delete("/connections/{connection_id}")
async def delete_connection(connection_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    conn = await db.get(Connection, connection_id)
    if not conn or conn.user_id != user.id:
        raise HTTPException(404, "Connection not found")
    was_bot = conn.provider == "telegram_bot"
    token = None
    if was_bot and (conn.config or {}).get("webhook_registered"):
        from ..security import decrypt_config
        token = decrypt_config(conn.config).get("bot_token")
    await db.delete(conn)
    await db.commit()
    if token and settings.effective_telegram_mode == "webhook":
        try:
            await telegram_service.tg_call(token, "deleteWebhook", {})
        except telegram_service.TelegramError:
            pass
    return {"deleted": connection_id}


# ───────── Google OAuth ─────────

def _make_state(user_id: int, provider: str, name: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(
        {"u": user_id, "p": provider, "n": name, "t": int(utcnow().timestamp())}).encode()).decode()
    return f"{payload}.{sign(payload, 'oauth-state', 40)}"


def _read_state(state: str) -> dict:
    try:
        payload, sig = state.rsplit(".", 1)
        if not constant_eq(sig, sign(payload, "oauth-state", 40)):
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        if int(utcnow().timestamp()) - int(data["t"]) > 600:
            raise ValueError
        return data
    except Exception:
        raise HTTPException(400, "Invalid state")


@router.get("/oauth/google/start")
async def google_oauth_start(provider: str, name: str, user: User = Depends(get_current_user)):
    """Возвращает ссылку на экран согласия Google — фронтенд делает на неё редирект."""
    if provider not in GOOGLE_SCOPES:
        raise HTTPException(400, f"Unknown Google provider: {provider}")
    if not settings.google_client_id:
        raise HTTPException(500, "GOOGLE_CLIENT_ID не задан в .env — сначала заведи OAuth-приложение в Google Cloud Console")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect,
        "response_type": "code",
        "scope": GOOGLE_SCOPES[provider],
        "access_type": "offline",   # без этого Google не выдаст refresh_token
        "prompt": "consent",        # иначе refresh_token придёт только при первом согласии
        "state": _make_state(user.id, provider, name),
    }
    return {"auth_url": f"{settings.google_auth_url}?{urlencode(params)}"}


@router.get("/oauth/google/callback")
async def google_oauth_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    """Google возвращает пользователя сюда. Подлинность и владелец определяются подписанным state."""
    data = _read_state(state)
    user = await db.get(User, data["u"])
    base = settings.app_url
    if not user or not user.is_active:
        return RedirectResponse(url=f"{base}/connections?error=google_oauth_failed")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(settings.google_token_url, data={
            "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect, "grant_type": "authorization_code",
        })
    if response.status_code != 200:
        return RedirectResponse(url=f"{base}/connections?error=google_oauth_failed")
    tokens = response.json()

    db.add(Connection(user_id=user.id, category="tool", provider=data["p"], name=data["n"], config=encrypt_config({
        "access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token"),
        "expires_in": tokens.get("expires_in", 3600), "obtained_at": datetime.now(timezone.utc).isoformat(),
    })))
    await db.commit()
    return RedirectResponse(url=f"{base}/connections?connected=1")
