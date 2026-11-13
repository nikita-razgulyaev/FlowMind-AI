import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Connection, User, utcnow
from ..schemas import ConnectionCreate
from ..security import encrypt_config, mask_config
from ..services import caldav, email_service, oauth, telegram_service
from ..services.ssrf import assert_public_url

router = APIRouter(tags=["connections"])

MAX_CONNECTIONS_PER_USER = 30
PROVIDERS = {
    "huggingface": "ai_api", "openai_compatible": "ai_api", "telegram_bot": "tool", "email": "tool", "yandex_calendar": "tool",
    **{provider: "tool" for provider in oauth.OAUTH_PROVIDERS},
}
def email_service_ok(value: str) -> bool:
    return textops_email_ok(value)


def textops_email_ok(value: str) -> bool:
    from ..services.textops import EMAIL_RE
    return bool(EMAIL_RE.fullmatch(value or ""))


@router.get("/connections/email-presets")
async def email_presets(user: User = Depends(get_current_user)):
    return [{"id": key, "label": v["label"], "help": v["help"], "custom": key == "custom"} for key, v in email_service.PRESETS.items()]


BOT_TOKEN_RE = re.compile(r"^\d{3,}:[A-Za-z0-9_-]{20,}$")


def _dto(c: Connection) -> dict:
    return {"id": c.id, "category": c.category, "provider": c.provider, "name": c.name,
            "config": mask_config({k: v for k, v in (c.config or {}).items() if k != "webhook_registered"}),
            "oauth": c.provider in oauth.OAUTH_PROVIDERS,
            "needs_reauth": bool((c.config or {}).get("needs_reauth")),
            "account": (c.config or {}).get("email") or (c.config or {}).get("account") or "",
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
    if data.provider in oauth.OAUTH_PROVIDERS:
        raise HTTPException(400, detail={"code": "use_oauth", "message": "Это подключение создаётся через вход в аккаунт сервиса, а не вводом пароля"})
    count = (await db.execute(select(func.count()).select_from(Connection).where(Connection.user_id == user.id))).scalar_one()
    if count >= MAX_CONNECTIONS_PER_USER:
        raise HTTPException(400, detail={"code": "too_many_connections", "message": f"Максимум {MAX_CONNECTIONS_PER_USER} подключений"})

    config = dict(data.config)
    if data.provider == "telegram_bot" and not BOT_TOKEN_RE.match(str(config.get("bot_token", ""))):
        raise HTTPException(400, detail={"code": "bad_bot_token", "message": "Неверный формат токена бота (ожидается 123456:ABC...)"})
    if data.provider == "yandex_calendar":
        email_, password_ = str(config.get("email", "")).strip(), str(config.get("password", ""))
        if not email_service_ok(email_) or not password_:
            raise HTTPException(400, detail={"code": "bad_calendar", "message": "Укажите адрес Яндекс Почты и пароль приложения для типа «Календарь»"})
        try:
            await caldav.check_credentials(email_, password_)
        except caldav.CalDAVError as e:
            raise HTTPException(400, detail={"code": "calendar_login_failed", "message": str(e)})
        except Exception:
            raise HTTPException(400, detail={"code": "calendar_unreachable", "message": "Не удалось связаться с Яндекс Календарём. Повторите попытку позже"})
        config = {"email": email_, "password": password_, "account": email_}
    if data.provider == "telegram_bot":
        try:                                       # Telegram сам подтверждает, что токен рабочий, и называет бота
            me = (await telegram_service.tg_call(str(config["bot_token"]), "getMe")).get("result")
        except telegram_service.TelegramError:
            raise HTTPException(400, detail={"code": "bad_bot_token", "message": "Telegram не принял токен. Скопируйте его из @BotFather целиком"})
        if isinstance(me, dict) and me.get("username"):
            config["account"] = f"@{me['username']}"
    if data.provider == "openai_compatible" and config.get("base_url"):
        try:
            await assert_public_url(str(config["base_url"]))
        except ValueError as e:
            raise HTTPException(400, detail={"code": "bad_url", "message": str(e)})

    if data.provider == "email":
        resolved = email_service.resolve_settings(config)
        if not textops_email_ok(resolved["email"]) or not resolved["password"]:
            raise HTTPException(400, detail={"code": "bad_email", "message": "Укажите адрес почты и пароль (для Gmail, Mail.ru и Яндекса — пароль приложения)"})
        if not resolved["imap_host"] or not resolved["smtp_host"]:
            raise HTTPException(400, detail={"code": "bad_email", "message": "Укажите адреса почтовых серверов (IMAP и SMTP)"})
        for host in (resolved["imap_host"], resolved["smtp_host"]):
            try:
                await assert_public_url(f"https://{host}")
            except ValueError as e:
                raise HTTPException(400, detail={"code": "bad_url", "message": str(e)})
        try:
            await email_service.check_credentials(config)
        except Exception:
            raise HTTPException(400, detail={"code": "email_login_failed", "message": "Не удалось войти в почту. Проверьте адрес, пароль приложения и включён ли доступ по IMAP"})

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
    if conn.provider in oauth.OAUTH_PROVIDERS:
        from ..security import decrypt_config
        await oauth.revoke(conn.provider, decrypt_config(conn.config))
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


# ───────── OAuth-вход (Google, Яндекс, Mail.ru) ─────────

@router.get("/oauth/status")
async def oauth_status(user: User = Depends(get_current_user)):
    """Какие сервисы входа настроены на сервере: для остальных кнопка входа показывает подсказку администратору."""
    return {family: oauth.is_configured(family) for family in oauth.FAMILIES}


@router.get("/oauth/start")
async def oauth_start(provider: str, name: str, reconnect_id: Optional[int] = None, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """Возвращает ссылку на экран согласия сервиса — фронтенд делает на неё редирект. reconnect_id — повторный вход в существующее подключение."""
    if provider not in oauth.OAUTH_PROVIDERS:
        raise HTTPException(400, f"Unknown OAuth provider: {provider}")
    if reconnect_id is not None:
        existing = await db.get(Connection, reconnect_id)
        if not existing or existing.user_id != user.id or existing.provider != provider:
            raise HTTPException(404, "Connection not found")
    state, nonce = oauth.make_state(user.id, provider, name.strip()[:100] or provider, reconnect_id)
    return {"auth_url": oauth.build_auth_url(provider, state, nonce)}


@router.get("/oauth/google/start")        # прежний адрес, оставлен для совместимости
async def google_oauth_start(provider: str, name: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if oauth.PROVIDERS.get(provider, {}).get("family") != "google":
        raise HTTPException(400, f"Unknown Google provider: {provider}")
    return await oauth_start(provider, name, None, user, db)


async def _finish_oauth(family: str, code: Optional[str], state: Optional[str], error: Optional[str], db: AsyncSession):
    base = settings.app_url
    fail = lambda reason, provider="": RedirectResponse(url=f"{base}/connections?error={reason}" + (f"&provider={provider}" if provider else ""))
    if family not in oauth.FAMILIES:
        raise HTTPException(404, "Unknown OAuth service")
    if not state:
        return fail("oauth_failed")
    data = oauth.read_state(state)
    provider = data["p"]
    if oauth.family_of(provider) != family:
        return fail("oauth_failed", provider)
    if error or not code:                         # пользователь отказал в доступе
        return fail("oauth_denied", provider)
    user = await db.get(User, data["u"])
    if not user or not user.is_active:
        return fail("oauth_failed", provider)

    try:
        tokens = await oauth.exchange_code(provider, code, data["r"])
    except HTTPException:
        return fail("oauth_failed", provider)
    if oauth.missing_scopes(provider, tokens):
        await oauth.revoke(provider, tokens)
        return fail("missing_scope", provider)
    tokens.update(await oauth.fetch_account(provider, tokens))
    if provider in oauth.MAIL_PROVIDERS and not tokens.get("email"):
        return fail("no_email", provider)

    config = encrypt_config(tokens)
    if data.get("c"):                              # повторный вход: обновляем то же подключение
        conn = await db.get(Connection, data["c"])
        if not conn or conn.user_id != user.id or conn.provider != provider:
            return fail("oauth_failed", provider)
        conn.config = config
        db.add(conn)
    else:
        count = (await db.execute(select(func.count()).select_from(Connection).where(Connection.user_id == user.id))).scalar_one()
        if count >= MAX_CONNECTIONS_PER_USER:
            return fail("too_many_connections", provider)
        db.add(Connection(user_id=user.id, category="tool", provider=provider, name=data["n"], config=config))
    await db.commit()
    return RedirectResponse(url=f"{base}/connections?connected=1&provider={provider}")


@router.get("/oauth/{family}/callback")
async def oauth_callback(family: str, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None,
                         db: AsyncSession = Depends(get_db)):
    """Сервис возвращает пользователя сюда. Подлинность и владелец определяются подписанным state."""
    return await _finish_oauth(family, code, state, error, db)
