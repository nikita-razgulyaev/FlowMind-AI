from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import (Connection, EmailToken, Execution, Payment, RefreshToken, Subscription,
                      UsageCounter, User, Workflow)
from ..security import hash_password, verify_password
from ..services import telegram_service
from ..services.limits import count_workflows, get_subscription, get_usage, get_user_plan
from .auth import COOKIE, COOKIE_PATH, user_dto
from .dto import plan_dto, subscription_dto

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    plan = await get_user_plan(db, user)
    sub = await get_subscription(db, user)
    return {
        "user": user_dto(user),
        "plan": plan_dto(plan),
        "subscription": subscription_dto(sub),
        "usage": await get_usage(db, user.id),
        "workflows": await count_workflows(db, user.id),
    }


class ProfileIn(BaseModel):
    name: str = Field(max_length=120)


@router.patch("")
async def update_profile(data: ProfileIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.name = data.name.strip()
    await db.commit()
    return user_dto(user)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/password")
async def change_password(data: PasswordIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.is_local:
        raise HTTPException(400, detail={"code": "local_user", "message": "У локального пользователя нет пароля"})
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, detail={"code": "bad_password", "message": "Текущий пароль указан неверно"})
    user.password_hash = hash_password(data.new_password)
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    await db.commit()
    return {"ok": True}


class DeleteAccountIn(BaseModel):
    password: str


@router.delete("")
async def delete_account(data: DeleteAccountIn, response: Response, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if user.is_local:
        raise HTTPException(400, detail={"code": "local_user", "message": "Локального пользователя удалить нельзя"})
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(400, detail={"code": "bad_password", "message": "Пароль указан неверно"})
    if user.role == "admin":
        admins = (await db.execute(select(User).where(User.role == "admin", User.is_active.is_(True)))).scalars().all()
        if len(admins) <= 1:
            raise HTTPException(400, detail={"code": "last_admin", "message": "Нельзя удалить единственного администратора"})

    await db.execute(update(Workflow).where(Workflow.user_id == user.id).values(is_active=False))
    await telegram_service.sync_user_webhooks(db, user.id)           # снимаем вебхуки, пока подключения ещё есть
    for model in (Execution, Workflow, Connection, UsageCounter, RefreshToken, EmailToken, Subscription):
        await db.execute(delete(model).where(model.user_id == user.id))
    await db.execute(update(Payment).where(Payment.user_id == user.id).values(user_id=None))   # платежи остаются для учёта
    await db.delete(user)
    await db.commit()
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return {"ok": True}


@router.get("/settings")
async def get_settings(user: User = Depends(get_current_user)):
    return user.settings or {}


@router.put("/settings")
async def put_settings(data: Dict[str, Any], user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    allowed = {"defaultMode", "defaultLocalModel", "defaultCloudModel", "defaultTemperature", "theme", "language"}
    clean = {k: v for k, v in data.items() if k in allowed}
    user.settings = clean
    await db.commit()
    return clean
