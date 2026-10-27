"""Фоновые задачи: автопродление подписок и чистка устаревших данных."""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete

from ..database import async_session
from ..models import EmailToken, Execution, RefreshToken, TelegramUpdate, utcnow
from . import billing

log = logging.getLogger("flowmind.maintenance")
MAX_HISTORY_DAYS = 365


async def cleanup(db) -> None:
    now = utcnow()
    await db.execute(delete(TelegramUpdate).where(TelegramUpdate.created_at < now - timedelta(days=3)))
    await db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now - timedelta(days=7)))
    await db.execute(delete(EmailToken).where(EmailToken.expires_at < now - timedelta(days=7)))
    await db.execute(delete(Execution).where(Execution.started_at < now - timedelta(days=MAX_HISTORY_DAYS)))
    await db.commit()


async def scheduler_loop() -> None:
    tick = 0
    while True:
        try:
            async with async_session() as db:
                stats = await billing.process_renewals(db)
                if stats:
                    log.info("Продления подписок: %s", stats)
                if tick % 60 == 0:                       # раз в час
                    await cleanup(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой фоновой задачи")
        tick += 1
        await asyncio.sleep(60)
