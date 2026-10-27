from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import EmailToken, RefreshToken, Subscription, User, utcnow
from ..schemas import LoginIn, RegisterIn
from ..security import (create_access_token, hash_password, hash_token, new_token, verify_password)
from ..services.mailer import send_email
from ..services.ratelimit import client_ip, email_limiter, login_limiter, register_limiter

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "fm_refresh"
COOKIE_PATH = "/api/auth"


def user_dto(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "email_verified": u.email_verified,
            "is_local": u.is_local, "created_at": u.created_at}


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=settings.refresh_token_days * 86400, httponly=True,
                        samesite="lax", secure=settings.secure_cookies, path=COOKIE_PATH)


async def issue_session(db: AsyncSession, user: User, request: Request, response: Response) -> dict:
    raw = new_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hash_token(raw),
                        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
                        user_agent=request.headers.get("user-agent", "")[:250]))
    user.last_login_at = utcnow()
    await db.commit()
    _set_cookie(response, raw)
    return {"access_token": create_access_token(user.id), "user": user_dto(user)}


async def _send_token_email(db: AsyncSession, user: User, kind: str) -> Optional[str]:
    raw = new_token()
    hours = 24 if kind == "verify" else 1
    db.add(EmailToken(user_id=user.id, kind=kind, token_hash=hash_token(raw), expires_at=utcnow() + timedelta(hours=hours)))
    await db.commit()
    if kind == "verify":
        link = f"{settings.app_url}/verify-email?token={raw}"
        await send_email(user.email, "Подтвердите email — FlowMind AI",
                         f"Здравствуйте!\n\nПодтвердите адрес, перейдя по ссылке (действует 24 часа):\n{link}\n")
    else:
        link = f"{settings.app_url}/reset-password?token={raw}"
        await send_email(user.email, "Сброс пароля — FlowMind AI",
                         f"Вы запросили сброс пароля. Ссылка действует 1 час:\n{link}\n\nЕсли это были не вы, просто проигнорируйте письмо.")
    return link if settings.demo_mode else None


@router.post("/register")
async def register(data: RegisterIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    register_limiter.check(client_ip(request), "Слишком много регистраций с вашего адреса, попробуйте позже")
    email = data.email.lower()
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, detail={"code": "email_taken", "message": "Пользователь с таким email уже существует"})

    is_admin = bool(settings.admin_email) and email == settings.admin_email.strip().lower()
    user = User(email=email, name=data.name.strip(), password_hash=hash_password(data.password),
                role="admin" if is_admin else "user",
                email_verified=is_admin or not settings.require_email_verification)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    db.add(Subscription(user_id=user.id, plan_code="free"))
    await db.commit()

    if not user.email_verified:
        link = await _send_token_email(db, user, "verify")
        return {"verification_required": True, "dev_link": link}
    return {"verification_required": False, **(await issue_session(db, user, request, response))}


@router.post("/login")
async def login(data: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    email = data.email.lower()
    login_limiter.check(f"{client_ip(request)}:{email}", "Слишком много попыток входа, подождите несколько минут")
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, detail={"code": "bad_credentials", "message": "Неверный email или пароль"})
    if not user.is_active:
        raise HTTPException(403, detail={"code": "user_blocked", "message": "Аккаунт заблокирован"})
    if settings.require_email_verification and not user.email_verified:
        raise HTTPException(403, detail={"code": "email_not_verified", "message": "Подтвердите email — письмо отправлено при регистрации"})
    return await issue_session(db, user, request, response)


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get(COOKIE)
    if not raw:
        raise HTTPException(401, detail={"code": "no_session", "message": "Нет активной сессии"})
    rec = (await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))).scalar_one_or_none()
    if not rec or rec.revoked or rec.expires_at < utcnow():
        response.delete_cookie(COOKIE, path=COOKIE_PATH)
        raise HTTPException(401, detail={"code": "session_expired", "message": "Сессия истекла"})
    user = await db.get(User, rec.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, detail={"code": "session_expired", "message": "Сессия истекла"})
    rec.revoked = True                                      # ротация refresh-токена
    await db.commit()
    return await issue_session(db, user, request, response)


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get(COOKIE)
    if raw:
        await db.execute(update(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)).values(revoked=True))
        await db.commit()
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return {"ok": True}


class TokenIn(BaseModel):
    token: str


class EmailIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


async def _consume(db: AsyncSession, raw: str, kind: str) -> User:
    rec = (await db.execute(select(EmailToken).where(EmailToken.token_hash == hash_token(raw), EmailToken.kind == kind))).scalar_one_or_none()
    if not rec or rec.used_at or rec.expires_at < utcnow():
        raise HTTPException(400, detail={"code": "bad_token", "message": "Ссылка недействительна или устарела"})
    user = await db.get(User, rec.user_id)
    if not user:
        raise HTTPException(400, detail={"code": "bad_token", "message": "Ссылка недействительна или устарела"})
    rec.used_at = utcnow()
    return user


@router.post("/verify-email")
async def verify_email(data: TokenIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    user = await _consume(db, data.token, "verify")
    user.email_verified = True
    await db.commit()
    return await issue_session(db, user, request, response)


@router.post("/resend-verification")
async def resend_verification(data: EmailIn, request: Request, db: AsyncSession = Depends(get_db)):
    email_limiter.check(f"{client_ip(request)}:verify", "Слишком много запросов писем")
    user = (await db.execute(select(User).where(User.email == data.email.lower()))).scalar_one_or_none()
    link = None
    if user and not user.email_verified and user.is_active:
        link = await _send_token_email(db, user, "verify")
    return {"ok": True, "dev_link": link}


@router.post("/forgot-password")
async def forgot_password(data: EmailIn, request: Request, db: AsyncSession = Depends(get_db)):
    email_limiter.check(f"{client_ip(request)}:reset", "Слишком много запросов писем")
    user = (await db.execute(select(User).where(User.email == data.email.lower()))).scalar_one_or_none()
    link = None
    if user and user.is_active and user.password_hash:
        link = await _send_token_email(db, user, "reset")
    return {"ok": True, "dev_link": link}            # ответ одинаков, существует ли email — не раскрываем


@router.post("/reset-password")
async def reset_password(data: ResetIn, db: AsyncSession = Depends(get_db)):
    user = await _consume(db, data.token, "reset")
    user.password_hash = hash_password(data.password)
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    await db.commit()
    return {"ok": True}
