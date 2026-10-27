import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Connection, User
from ..security import constant_eq
from ..services import telegram_service as tg

router = APIRouter(prefix="/telegram", tags=["telegram"])
_background: set[asyncio.Task] = set()


@router.post("/webhook/{connection_id}")
async def webhook(connection_id: int, request: Request, x_telegram_bot_api_secret_token: str = Header(default="")):
    """Telegram присылает сюда обновления бота. Подлинность проверяется секретом, заданным при setWebhook."""
    if not constant_eq(x_telegram_bot_api_secret_token, tg.webhook_secret(connection_id)):
        raise HTTPException(403, "Forbidden")
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(400, "Bad update")
    task = asyncio.create_task(tg.handle_update(connection_id, update))      # отвечаем сразу, чтобы Telegram не повторял доставку
    _background.add(task)
    task.add_done_callback(_background.discard)
    return {"ok": True}


@router.get("/status")
async def status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    conns = (await db.execute(select(Connection).where(
        Connection.user_id == user.id, Connection.provider == "telegram_bot"))).scalars().all()
    return {
        "mode": settings.effective_telegram_mode,
        "public_url_configured": bool(settings.base_url),
        "connections": [{"id": c.id, "name": c.name, "webhook_registered": bool((c.config or {}).get("webhook_registered"))} for c in conns],
    }


@router.post("/sync")
async def sync(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Переустанавливает вебхуки ботов пользователя (кнопка «Переподключить»)."""
    return {"mode": settings.effective_telegram_mode, "results": await tg.sync_user_webhooks(db, user.id)}
