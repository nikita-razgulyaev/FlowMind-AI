"""Фоновые задачи: автопродление подписок и чистка устаревших данных."""
import asyncio
import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select

from ..config import settings
from ..database import async_session
from ..models import Connection, EmailToken, Execution, RefreshToken, TelegramUpdate, User, Workflow, utcnow
from . import billing, email_service, oauth
from .google import refresh_if_needed
from ..security import decrypt_config
from .runner import run_workflow

log = logging.getLogger("flowmind.maintenance")
MAX_HISTORY_DAYS = 365
MAX_INTERVAL_MINUTES = 7 * 24 * 60
_last_uid: dict[tuple[int, str], int] = {}            # (workflow_id, node_id) -> UID последнего обработанного письма (сбрасывается при рестарте)
_last_polled: dict[tuple[int, str], object] = {}
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


async def _poll_mailbox(workflow_id: int, node_id: str, connection_id, key) -> None:
    async with async_session() as db:
        wf = await db.get(Workflow, workflow_id)
        user = await db.get(User, wf.user_id) if wf else None
        conn = await db.get(Connection, int(connection_id)) if str(connection_id or "").isdigit() else None
        if not wf or not wf.is_active or not user or not user.is_active or not conn or conn.user_id != user.id or conn.provider not in oauth.MAIL_PROVIDERS:
            return
        try:
            cfg = await refresh_if_needed(conn, db) if conn.provider in oauth.OAUTH_PROVIDERS else decrypt_config(conn.config)
            if cfg.get("needs_reauth"):
                return
            last_uid, letters = await email_service.fetch_new({**cfg, "_provider": conn.provider}, _last_uid.get(key))
        except Exception:
            log.warning("Не удалось проверить почту для workflow %s", workflow_id)
            return
        _last_uid[key] = last_uid
        for letter in letters:
            trigger = {"input": f"{letter['subject']}\n\n{letter['body']}".strip(), "email": letter}
            try:
                await run_workflow(db, user, wf, trigger, source="email")
            except HTTPException as e:
                log.info("Email workflow %s пропущен: %s", workflow_id, e.detail)
            except Exception:
                log.exception("Сбой Email-запуска workflow %s", workflow_id)


async def run_due_mail_polls(db) -> int:
    """Проверяет ящики воркфлоу с нодой «Новое письмо». Первая проверка только запоминает последнее письмо: старая почта не обрабатывается."""
    now = utcnow()
    seen, started = set(), 0
    for wf in (await db.execute(select(Workflow).where(Workflow.is_active.is_(True)))).scalars().all():
        for node in wf.nodes or []:
            if node.get("type") != "email_trigger":
                continue
            cfg = node.get("config") or {}
            raw = cfg.get("interval_minutes")
            interval = max(min_interval_minutes(), min(int(raw) if str(raw).isdigit() else 5, 1440))
            key = (wf.id, node["id"])
            seen.add(key)
            last = _last_polled.get(key)
            if last is None or now - last >= timedelta(minutes=interval) - timedelta(seconds=5):
                _last_polled[key] = now
                asyncio.create_task(_poll_mailbox(wf.id, node["id"], cfg.get("connection_id"), key))
                started += 1
    for key in set(_last_polled) - seen:
        _last_polled.pop(key, None)
        _last_uid.pop(key, None)
    return started


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
                await run_due_mail_polls(db)
                if tick % 60 == 0:                       # раз в час
                    await cleanup(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой фоновой задачи")
        tick += 1
        await asyncio.sleep(60)
