"""Приём обращений с формы обратной связи. Доступен и гостям, и вошедшим пользователям."""
import re
from typing import Literal, Optional

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Feedback, User
from ..security import decode_access_token
from ..services.feedback import clean_page, detect_spam, forward_to_formspree
from ..services.limits import effective_plan_code, get_subscription
from ..services.ratelimit import client_ip, feedback_burst_limiter, feedback_hour_limiter

router = APIRouter(prefix="/feedback", tags=["feedback"])

MESSAGE_MIN = 3
MESSAGE_MAX = 3000
_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class FeedbackIn(BaseModel):
    type: Literal["question", "bug", "idea", "payment", "other"] = "other"
    message: str = Field(max_length=MESSAGE_MAX * 2)
    name: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=320)
    page: str = Field(default="", max_length=500)
    client_id: Optional[str] = Field(default=None, max_length=64)      # один на открытие формы: повторная отправка не создаёт дубль
    hp: str = Field(default="", max_length=10_000)                     # ловушка для ботов: у людей всегда пустое
    elapsed_ms: Optional[float] = Field(default=None, ge=0, le=86_400_000)   # сколько форма была открыта до отправки

    @field_validator("message")
    @classmethod
    def _message(cls, v: str) -> str:
        v = v.strip()
        if len(v) < MESSAGE_MIN:
            raise ValueError(f"Напишите хотя бы {MESSAGE_MIN} символа")
        if len(v) > MESSAGE_MAX:
            raise ValueError(f"Сообщение слишком длинное (максимум {MESSAGE_MAX} символов)")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if not v:
            return ""
        try:
            return validate_email(v, check_deliverability=False).normalized
        except EmailNotValidError:
            raise ValueError("Некорректный email") from None

    @field_validator("client_id")
    @classmethod
    def _client_id(cls, v: Optional[str]) -> Optional[str]:
        return v if v and _CLIENT_ID_RE.match(v) else None            # кривой ключ просто игнорируем, обращение всё равно принимаем


async def _optional_user(request: Request, db: AsyncSession) -> Optional[User]:
    """Пользователь, если приложен действующий токен. Просроченный токен не должен мешать отправить отзыв — тогда это гость."""
    if not settings.auth_required:
        return None
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    user_id = decode_access_token(header[7:].strip())
    user = await db.get(User, user_id) if user_id else None
    return user if user and user.is_active else None


@router.post("")
async def send_feedback(data: FeedbackIn, request: Request, background: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    if not settings.feedback_on:
        raise HTTPException(404, detail={"code": "feedback_disabled", "message": "Форма обратной связи отключена"})

    ip = client_ip(request)
    feedback_burst_limiter.check(ip, "Слишком часто. Подождите минуту и отправьте ещё раз")
    feedback_hour_limiter.check(ip, "Слишком много обращений с вашего адреса. Попробуйте позже или напишите нам на почту")

    if data.client_id:        # повтор после обрыва связи или двойной клик: первое обращение уже сохранено
        if (await db.execute(select(Feedback.id).where(Feedback.client_id == data.client_id))).first():
            return {"ok": True}

    user = await _optional_user(request, db)
    reason = detect_spam(data.hp, data.elapsed_ms, data.message)
    forward = bool(settings.formspree_endpoint) and not reason
    fb = Feedback(
        client_id=data.client_id,
        user_id=user.id if user else None,
        name=data.name or (user.name if user else "") or "",
        email=data.email or (user.email if user else ""),
        plan=effective_plan_code(await get_subscription(db, user)) if user else "",
        type=data.type,
        message=data.message,
        page=clean_page(data.page),
        user_agent=request.headers.get("user-agent", "")[:300],
        status="spam" if reason else "new",
        spam_reason=reason,
        forward_status="pending" if forward else "off",
    )
    db.add(fb)
    try:
        await db.commit()
    except IntegrityError:          # две одинаковые отправки пришли одновременно — вторая и есть дубль
        await db.rollback()
        return {"ok": True}
    if forward:
        background.add_task(forward_to_formspree, fb.id)
    # Боту отвечаем так же, как человеку: пусть не знает, что его заметили.
    return {"ok": True}
