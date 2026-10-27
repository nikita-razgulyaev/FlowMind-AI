from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..services.platform_ai import get_app_setting

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/config")
async def public_config(db: AsyncSession = Depends(get_db)):
    """Публичные параметры развёртывания — по ним фронтенд решает, что показывать."""
    ai_enabled = bool(await get_app_setting(db, "ai_enabled", True))
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
