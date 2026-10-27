"""Защита ключа платформы: рубильник «AI выключен» и общий суточный потолок запросов."""
from sqlalchemy import select

from ..config import settings
from ..database import async_session
from ..models import AppSetting
from .limits import bump_global, get_global


class AIUnavailable(Exception):
    pass


async def get_app_setting(db, key: str, default=None):
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    return default if row is None or row.value is None else row.value


async def set_app_setting(db, key: str, value) -> None:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    await db.commit()


async def platform_guard() -> None:
    """Вызывается перед каждым обращением к LLM по ключу платформы."""
    async with async_session() as db:
        if not await get_app_setting(db, "ai_enabled", True):
            raise AIUnavailable("AI платформы временно отключён администратором. Подключите свой API-ключ в разделе «Подключения».")
        cap = int(await get_app_setting(db, "ai_daily_cap", settings.ai_daily_cap))
        used = await get_global(db, "platform_ai_calls")
        if used >= cap:
            raise AIUnavailable("Суточный лимит AI-запросов сервиса исчерпан. Попробуйте завтра или подключите свой API-ключ.")
        await bump_global(db, "platform_ai_calls")
