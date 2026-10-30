import asyncio
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Payment, Plan, User, utcnow
from ..payments import get_provider
from ..payments import mock as mock_pay
from ..services import billing
from ..services.limits import get_subscription
from .dto import plan_dto, subscription_dto

router = APIRouter(tags=["billing"])


@router.get("/plans")
async def list_plans(db: AsyncSession = Depends(get_db)):
    plans = (await db.execute(select(Plan).where(Plan.is_public.is_(True)).order_by(Plan.sort_order))).scalars().all()
    return [plan_dto(p) for p in plans]


@router.get("/billing/subscription")
async def my_subscription(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return subscription_dto(await get_subscription(db, user))


class PlanChoiceIn(BaseModel):
    plan_code: str
    period: str = Field(pattern="^(month|year)$")


@router.post("/billing/quote")
async def quote(data: PlanChoiceIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    q, plan, sub = await billing.make_quote(db, user, data.plan_code, data.period)
    return {"action": q.action, "kind": q.kind, "price": q.price, "credit": q.credit, "amount": q.amount,
            "plan": plan_dto(plan), "period": data.period, "effective_at": sub.current_period_end}


@router.post("/billing/checkout")
async def checkout(data: PlanChoiceIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.is_local:
        raise HTTPException(400, detail={"code": "local_user", "message": "В локальной версии тарифы не используются"})
    return await billing.start_checkout(db, user, data.plan_code, data.period)


@router.post("/billing/cancel")
async def cancel(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await billing.start_checkout(db, user, "free", "month")


@router.get("/billing/payments")
async def my_payments(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Payment).where(Payment.user_id == user.id).order_by(Payment.id.desc()).limit(100))).scalars().all()
    return [billing.payment_dto(p) for p in rows]


async def _own_payment(db: AsyncSession, user: User, payment_id: int) -> Payment:
    p = await db.get(Payment, payment_id)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Payment not found")
    return p


@router.get("/billing/payments/{payment_id}")
async def payment_status(payment_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await _own_payment(db, user, payment_id)
    # если вебхук не дошёл (например, локальная отладка) — уточняем статус у провайдера
    if p.status in ("pending", "requires_action") and p.provider == "yookassa" and p.provider_payment_id:
        try:
            result = await get_provider("yookassa").fetch_payment(p.provider_payment_id)
            await billing.apply_result(db, p, result)
        except Exception:
            pass
    return billing.payment_dto(p)


# ───────── ЮKassa: вебхук ─────────

@router.post("/billing/yookassa/webhook")
async def yookassa_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Уведомление ЮKassa. Статус не берём из тела — перепроверяем запросом к API."""
    try:
        body = await request.json()
        provider_id = body["object"]["id"]
    except Exception:
        raise HTTPException(400, "Bad notification")
    p = (await db.execute(select(Payment).where(Payment.provider == "yookassa", Payment.provider_payment_id == provider_id))).scalars().first()
    if p is None:
        return {"ok": True}                 # неизвестный платёж — отвечаем 200, чтобы ЮKassa не повторяла
    try:
        result = await get_provider("yookassa").fetch_payment(provider_id)
    except Exception:
        raise HTTPException(502, "Payment provider unavailable")      # ЮKassa повторит уведомление
    await billing.apply_result(db, p, result)
    return {"ok": True}


# ───────── Демо-оплата (PAYMENT_PROVIDER=mock) ─────────

def _require_mock() -> None:
    if settings.payment_provider != "mock":
        raise HTTPException(404, "Not found")


@router.get("/billing/test-cards")
async def test_cards():
    _require_mock()
    return mock_pay.TEST_CARDS


class CardIn(BaseModel):
    number: str = Field(max_length=32)
    exp_month: int
    exp_year: int
    cvc: str = Field(max_length=4)
    holder: str = Field("", max_length=80)


def _validate_card(card: CardIn) -> str:
    number = re.sub(r"[\s-]", "", card.number)
    if not number.isdigit() or not 13 <= len(number) <= 19 or not mock_pay.luhn_ok(number):
        raise HTTPException(422, detail={"code": "invalid_card", "message": "Некорректный номер карты"})
    year = card.exp_year + 2000 if card.exp_year < 100 else card.exp_year
    now = utcnow()
    if not 1 <= card.exp_month <= 12 or (year, card.exp_month) < (now.year, now.month):
        raise HTTPException(422, detail={"code": "invalid_card", "message": "Срок действия карты истёк или указан неверно"})
    if not re.fullmatch(r"\d{3,4}", card.cvc):
        raise HTTPException(422, detail={"code": "invalid_card", "message": "Некорректный CVC"})
    return number


async def _complete_mock_payment_later(payment_id: int, method_id: str | None, label: str | None, delay_sec: float = 10.0) -> None:
    """Фоновая имитация: через delay_sec pending → succeeded + активация подписки."""
    await asyncio.sleep(delay_sec)
    from ..database import async_session
    try:
        async with async_session() as db:
            p = await db.get(Payment, payment_id)
            if p is None or p.status != "pending":
                return
            await billing.finalize_success(db, p, method_id, label)
    except Exception:
        pass


@router.post("/billing/mock/{payment_id}/pay")
async def mock_pay_endpoint(payment_id: int, card: CardIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_mock()
    p = await _own_payment(db, user, payment_id)
    if p.provider != "mock" or p.status != "pending":
        raise HTTPException(400, detail={"code": "bad_state", "message": "Платёж нельзя оплатить в текущем состоянии"})
    number = _validate_card(card)
    status, reason = mock_pay.evaluate_card(number)
    method_id, label = mock_pay.method_for_card(number)
    p.meta = {**(p.meta or {}), "card": {"brand": mock_pay.card_brand(number), "last4": number[-4:]}}      # номер целиком не храним
    if status == "succeeded":
        # Не дублируем оплату: оставляем pending и через 10 с переводим в paid + выдаём подписку
        p.meta = {**(p.meta or {}), "pm": [method_id, label], "mock_scheduled": True}
        await db.commit()
        await db.refresh(p)
        asyncio.create_task(_complete_mock_payment_later(p.id, method_id, label, 10.0))
    elif status == "requires_action":
        p.status = "requires_action"
        p.meta = {**p.meta, "pm": [method_id, label]}
        await db.commit()
    else:
        p.status, p.failure_reason = "failed", reason
        await db.commit()
    return billing.payment_dto(p)


class ThreeDsIn(BaseModel):
    approve: bool


@router.post("/billing/mock/{payment_id}/confirm-3ds")
async def mock_confirm_3ds(payment_id: int, data: ThreeDsIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_mock()
    p = await _own_payment(db, user, payment_id)
    if p.provider != "mock" or p.status != "requires_action":
        raise HTTPException(400, detail={"code": "bad_state", "message": "Подтверждение не требуется"})
    if data.approve:
        method_id, label = (p.meta or {}).get("pm", [None, None])
        p.status = "pending"
        p.meta = {**(p.meta or {}), "pm": [method_id, label], "mock_scheduled": True}
        await db.commit()
        await db.refresh(p)
        asyncio.create_task(_complete_mock_payment_later(p.id, method_id, label, 10.0))
    else:
        p.status, p.failure_reason = "failed", "3-D Secure не пройден"
        await db.commit()
    return billing.payment_dto(p)


@router.post("/billing/demo/renew-now")
async def demo_renew_now(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Демо: «перематывает» конец периода на сейчас и запускает автопродление."""
    _require_mock()
    sub = await get_subscription(db, user)
    if sub.plan_code in ("free", "local"):
        raise HTTPException(400, detail={"code": "no_paid_plan", "message": "Нет платной подписки для продления"})
    sub.current_period_end = utcnow()
    sub.next_retry_at = None
    await db.commit()
    stats = await billing.process_renewals(db, user_id=user.id)
    await db.refresh(sub)
    return {"outcome": stats, "subscription": subscription_dto(sub)}


@router.post("/billing/demo/fail-next")
async def demo_fail_next(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Демо: следующее автосписание завершится отказом (имитация карты с нулевым балансом)."""
    _require_mock()
    sub = await get_subscription(db, user)
    if sub.plan_code in ("free", "local"):
        raise HTTPException(400, detail={"code": "no_paid_plan", "message": "Нет платной подписки"})
    sub.payment_method_id = f"mock_pm_fail_{utcnow().timestamp():.0f}"
    sub.payment_method_label = "Карта (демо: отказ списания)"
    await db.commit()
    return subscription_dto(sub)
