import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..config import settings
from ..database import async_session
from ..services.platform_ai import get_app_setting

log = logging.getLogger("flowmind.system")
router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    """Проверка живости процесса. БД проверяем мягко — 503, а не падение процесса."""
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        log.exception("health: database unreachable: %s", exc)
        return JSONResponse({"status": "degraded", "detail": "database unavailable"}, status_code=503)


@router.get("/config")
async def public_config():
    """Публичные параметры развёртывания — по ним фронтенд решает, что показывать.

    Не зависит жёстко от БД: при сбое отдаём значения из env, чтобы регистрация
    не показывала «Неизвестная ошибка» из‑за 502/500 на /api/config.
    """
    ai_enabled = True
    try:
        async with async_session() as db:
            ai_enabled = bool(await get_app_setting(db, "ai_enabled", True))
    except Exception as exc:
        log.warning("config: cannot read app settings (%s) — using defaults", exc)

    return {
        "deployment_mode": settings.deployment_mode.lower(),
        "auth_required": settings.auth_required,
        "payment_provider": settings.payment_provider,
        "demo_mode": settings.demo_mode,
        "require_email_verification": settings.require_email_verification,
        "default_llm_mode": settings.default_llm_mode,
        "ollama_model": settings.ollama_model,
        "platform_ai_available": bool(settings.platform_llm_api_key) and ai_enabled,
        "telegram_mode": settings.effective_telegram_mode,
        "languages": ["ru"],
    }
