from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import get_db
from .models import User
from .security import decode_access_token

LOCAL_EMAIL = "local@flowmind.local"


async def get_local_user(db: AsyncSession) -> User:
    user = (await db.execute(select(User).where(User.email == LOCAL_EMAIL))).scalar_one_or_none()
    if user is None:
        raise HTTPException(500, "Локальный пользователь не создан (ошибка инициализации)")
    return user


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    if not settings.auth_required:
        return await get_local_user(db)
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, detail={"code": "not_authenticated", "message": "Требуется вход"})
    user_id = decode_access_token(header[7:].strip())
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(401, detail={"code": "invalid_token", "message": "Сессия истекла, войдите заново"})
    if not user.is_active:
        raise HTTPException(403, detail={"code": "user_blocked", "message": "Аккаунт заблокирован"})
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, detail={"code": "forbidden", "message": "Недостаточно прав"})
    return user
