"""Telegram-триггер: приём входящих сообщений через webhook (облако) или long polling (локально)."""
import asyncio
import logging
from typing import Optional

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..database import async_session
from ..models import Connection, TelegramUpdate, User, Workflow
from ..security import decrypt_config, sign
from .ratelimit import telegram_chat_limiter
from .runner import run_workflow

log = logging.getLogger("flowmind.telegram")
TG_API = "https://api.telegram.org"


def bot_id(token: str) -> str:
    return token.split(":")[0]


def webhook_secret(connection_id: int) -> str:
    return sign(str(connection_id), "tg-webhook")


def webhook_url(connection_id: int) -> str:
    return f"{settings.base_url}/api/telegram/webhook/{connection_id}"


class TelegramError(Exception):
    pass


async def tg_call(token: str, method: str, payload: Optional[dict] = None, timeout: float = 15.0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{TG_API}/bot{token}/{method}", json=payload or {})
        data = r.json()
    except Exception as e:                                  # в тексте исключений может быть токен
        raise TelegramError(str(e).replace(token, "***"))
    if not data.get("ok"):
        raise TelegramError(str(data.get("description", "Telegram API error")))
    return data


def trigger_nodes(workflow: Workflow) -> list[dict]:
    return [n for n in (workflow.nodes or []) if n.get("type") == "telegram_trigger"]


async def workflows_for_connection(db, connection: Connection) -> list[Workflow]:
    rows = (await db.execute(select(Workflow).where(
        Workflow.user_id == connection.user_id, Workflow.is_active.is_(True), Workflow.has_telegram_trigger.is_(True),
    ))).scalars().all()
    return [w for w in rows if any((n.get("config") or {}).get("connection_id") == connection.id for n in trigger_nodes(w))]


async def sync_webhook(db, connection: Connection) -> dict:
    """Включает/выключает вебхук бота в зависимости от наличия активных воркфлоу с триггером."""
    mode = settings.effective_telegram_mode
    if mode != "webhook" or connection.provider != "telegram_bot":
        return {"mode": mode, "status": "not_applicable"}
    cfg = decrypt_config(connection.config)
    token = cfg.get("bot_token")
    if not token:
        return {"mode": mode, "status": "error", "error": "нет bot_token"}
    try:
        if await workflows_for_connection(db, connection):
            await tg_call(token, "setWebhook", {
                "url": webhook_url(connection.id), "secret_token": webhook_secret(connection.id),
                "allowed_updates": ["message"],
            })
            status = "registered"
            flag = True
        else:
            flag = False
            status = "idle"
            if (connection.config or {}).get("webhook_registered"):
                await tg_call(token, "deleteWebhook", {})
                status = "removed"
        stored = dict(connection.config or {})
        if bool(stored.get("webhook_registered")) != flag:
            stored["webhook_registered"] = flag
            connection.config = stored
            await db.commit()
        return {"mode": mode, "status": status}
    except TelegramError as e:
        return {"mode": mode, "status": "error", "error": str(e)}


async def sync_user_webhooks(db, user_id: int) -> list[dict]:
    if settings.effective_telegram_mode != "webhook":
        return []
    conns = (await db.execute(select(Connection).where(
        Connection.user_id == user_id, Connection.provider == "telegram_bot"))).scalars().all()
    return [{"connection_id": c.id, **(await sync_webhook(db, c))} for c in conns]


async def _notify(token: str, chat_id, text: str) -> None:
    try:
        await tg_call(token, "sendMessage", {"chat_id": chat_id, "text": text})
    except TelegramError:
        pass


async def handle_update(connection_id: int, update: dict) -> None:
    msg = update.get("message")
    if not msg or not msg.get("text") or "update_id" not in update:
        return
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    sender = msg.get("from") or {}
    text = msg["text"]

    async with async_session() as db:
        conn = await db.get(Connection, connection_id)
        if not conn or conn.provider != "telegram_bot":
            return
        token = decrypt_config(conn.config).get("bot_token")
        if not token:
            return
        try:
            db.add(TelegramUpdate(bot_id=bot_id(token), update_id=update["update_id"]))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return                                          # дубликат (повторная доставка)
        user = await db.get(User, conn.user_id)
        if not user or not user.is_active:
            return
        if not telegram_chat_limiter.allow(f"{connection_id}:{chat_id}"):
            return

        for wf in await workflows_for_connection(db, conn):
            node_cfg = next((n.get("config") or {} for n in trigger_nodes(wf)
                             if (n.get("config") or {}).get("connection_id") == connection_id), {})
            allowed = {s.strip() for s in str(node_cfg.get("allowed_chat_ids", "")).split(",") if s.strip()}
            if allowed and str(chat_id) not in allowed:
                continue
            if node_cfg.get("only_commands") and not text.startswith("/"):
                continue
            trigger = {"input": text, "telegram": {
                "chat_id": chat_id, "text": text, "username": sender.get("username", ""),
                "first_name": sender.get("first_name", ""), "message_id": msg.get("message_id"),
            }}
            try:
                await run_workflow(db, user, wf, trigger, source="telegram")
            except HTTPException as e:
                detail = e.detail if isinstance(e.detail, dict) else {}
                await _notify(token, chat_id, detail.get("message", "Не удалось выполнить сценарий"))
                break
            except Exception:
                log.exception("Ошибка выполнения Telegram-триггера (workflow %s)", wf.id)


class TelegramPoller:
    """Локальный режим: опрашивает getUpdates для каждого бота с активным триггером."""

    def __init__(self):
        self.tasks: dict[int, asyncio.Task] = {}
        self._supervisor: Optional[asyncio.Task] = None

    def start(self):
        self._supervisor = asyncio.create_task(self._supervise())

    async def stop(self):
        for t in [self._supervisor, *self.tasks.values()]:
            if t:
                t.cancel()
        await asyncio.gather(*[t for t in [self._supervisor, *self.tasks.values()] if t], return_exceptions=True)
        self.tasks.clear()

    async def _wanted(self) -> set[int]:
        async with async_session() as db:
            wfs = (await db.execute(select(Workflow).where(
                Workflow.is_active.is_(True), Workflow.has_telegram_trigger.is_(True)))).scalars().all()
            ids = {(n.get("config") or {}).get("connection_id") for w in wfs for n in trigger_nodes(w)}
            ids.discard(None)
            if not ids:
                return set()
            rows = (await db.execute(select(Connection.id).where(
                Connection.id.in_(ids), Connection.provider == "telegram_bot"))).scalars().all()
            return set(rows)

    async def _supervise(self):
        while True:
            try:
                wanted = await self._wanted()
                for cid in wanted - set(self.tasks):
                    self.tasks[cid] = asyncio.create_task(self._poll(cid))
                for cid in set(self.tasks) - wanted:
                    self.tasks.pop(cid).cancel()
                for cid, t in list(self.tasks.items()):
                    if t.done():
                        self.tasks.pop(cid, None)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Сбой supervisor-цикла Telegram")
            await asyncio.sleep(10)

    async def _poll(self, connection_id: int):
        offset: Optional[int] = None
        first = True
        while True:
            try:
                async with async_session() as db:
                    conn = await db.get(Connection, connection_id)
                    token = decrypt_config(conn.config).get("bot_token") if conn else None
                if not token:
                    return
                if first:
                    await tg_call(token, "deleteWebhook", {})
                    last = await tg_call(token, "getUpdates", {"offset": -1, "timeout": 0})
                    if last.get("result"):                  # пропускаем накопившиеся, пока сервис был выключен
                        offset = last["result"][-1]["update_id"] + 1
                    first = False
                payload = {"timeout": 25, "allowed_updates": ["message"]}
                if offset is not None:
                    payload["offset"] = offset
                data = await tg_call(token, "getUpdates", payload, timeout=40.0)
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    asyncio.create_task(handle_update(connection_id, upd))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("Telegram polling (подключение %s): %s", connection_id, e)
                await asyncio.sleep(5)


poller = TelegramPoller()
