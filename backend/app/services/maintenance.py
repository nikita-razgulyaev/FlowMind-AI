"""Фоновые задачи: автопродление подписок и чистка устаревших данных."""
import asyncio
import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select

from ..config import settings
from ..database import async_session
from ..models import EmailToken, Execution, RefreshToken, TelegramUpdate, User, Workflow, utcnow
from . import billing
from .runner import run_workflow

log = logging.getLogger("flowmind.maintenance")
MAX_HISTORY_DAYS = 365
MAX_INTERVAL_MINUTES = 7 * 24 * 60
_last_fired: dict[tuple[int, str], object] = {}      # (workflow_id, node_id) -> время последнего запуска (сбрасывается при рестарте)


def min_interval_minutes() -> int:
    return 1 if settings.is_local else 5               # в облаке чаще раза в 5 минут не запускаем


async def _fire_schedule(workflow_id: int, interval: int) -> None:
    async with async_session() as db:
        wf = await db.get(Workflow, workflow_id)
        user = await db.get(User, wf.user_id) if wf else None
        if not wf or not wf.is_active or not user or not user.is_active:
            return
        trigger = {"input": "", "schedule": {"fired_at": utcnow().isoformat(), "interval_minutes": interval}}
        try:
            await run_workflow(db, user, wf, trigger, source="schedule")
        except HTTPException as e:
            log.info("Schedule workflow %s пропущен: %s", workflow_id, e.detail)
        except Exception:
            log.exception("Сбой Schedule-запуска workflow %s", workflow_id)


async def run_due_schedules(db) -> int:
    """Запускает воркфлоу с нодой Schedule, у которых прошёл заданный интервал. Каждый запуск — отдельной задачей."""
    now = utcnow()
    seen, fired = set(), 0
    for wf in (await db.execute(select(Workflow).where(Workflow.is_active.is_(True)))).scalars().all():
        for node in wf.nodes or []:
            if node.get("type") != "schedule":
                continue
            raw = (node.get("config") or {}).get("interval_minutes")
            interval = max(min_interval_minutes(), min(int(raw) if str(raw).isdigit() else 60, MAX_INTERVAL_MINUTES))
            key = (wf.id, node["id"])
            seen.add(key)
            last = _last_fired.setdefault(key, now)       # первый раз только начинаем отсчёт
            if now - last >= timedelta(minutes=interval) - timedelta(seconds=5):
                _last_fired[key] = now
                asyncio.create_task(_fire_schedule(wf.id, interval))
                fired += 1
    for key in set(_last_fired) - seen:
        _last_fired.pop(key, None)
    return fired


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
                await run_due_schedules(db)
                if tick % 60 == 0:                       # раз в час
                    await cleanup(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой фоновой задачи")
        tick += 1
        await asyncio.sleep(60)
