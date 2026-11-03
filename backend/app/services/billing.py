"""Жизненный цикл подписки: расчёт цены, апгрейд с пересчётом, отложенный даунгрейд, продление, неудачные списания."""
from __future__ import annotations

import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Payment, Plan, Subscription, User, utcnow
from ..payments import PaymentResult, get_provider
from .limits import GRACE_DAYS, effective_plan_code, get_plan, get_subscription

MAX_RENEWAL_ATTEMPTS = 3
PERIODS = ("month", "year")


def add_period(dt: datetime, period: str) -> datetime:
    if period == "month":
        month = dt.month + 1
        year = dt.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return dt.replace(year=year, month=month, day=min(dt.day, monthrange(year, month)[1]))
    if period == "year":
        year = dt.year + 1
        return dt.replace(year=year, day=min(dt.day, monthrange(year, dt.month)[1]))
    raise ValueError("period must be month|year")


def price_for(plan: Plan, period: str) -> int:
    return plan.price_month if period == "month" else plan.price_year


def describe(plan: Plan, period: str) -> str:
    return f"FlowMind AI — тариф «{plan.name}», {'1 месяц' if period == 'month' else '1 год'}"


def payment_dto(p: Payment) -> dict:
    return {
        "id": p.id, "provider": p.provider, "plan_code": p.plan_code, "period": p.period, "kind": p.kind,
        "amount": p.amount, "plan_price": p.plan_price, "currency": p.currency, "status": p.status,
        "failure_reason": p.failure_reason, "confirmation_url": p.confirmation_url,
        "created_at": p.created_at, "paid_at": p.paid_at,
        "card": (p.meta or {}).get("card"),
    }


@dataclass
class Quote:
    action: str            # pay | schedule | cancel | resume
    kind: str = "initial"  # initial | upgrade
    price: int = 0
    credit: int = 0
    amount: int = 0


def _credit(sub: Subscription, now: datetime) -> int:
    if not (sub.current_period_start and sub.current_period_end and sub.amount_paid):
        return 0
    if sub.current_period_end <= now:
        return 0
    total = (sub.current_period_end - sub.current_period_start).total_seconds()
    left = (sub.current_period_end - now).total_seconds()
    if total <= 0:
        return 0
    return max(0, int(sub.amount_paid * min(1.0, left / total)))


async def make_quote(db: AsyncSession, user: User, plan_code: str, period: str) -> tuple[Quote, Plan, Subscription]:
    if period not in PERIODS:
        raise HTTPException(400, detail={"code": "bad_period", "message": "Период должен быть month или year"})
    plan = await get_plan(db, plan_code)
    sub = await get_subscription(db, user)
    now = utcnow()
    current_code = effective_plan_code(sub, now)

    if plan.code == "free":
        if current_code == "free":
            raise HTTPException(400, detail={"code": "already_free", "message": "У вас уже бесплатный тариф"})
        return Quote(action="cancel"), plan, sub
    if not plan.is_public or plan.code == "local":
        raise HTTPException(400, detail={"code": "bad_plan", "message": "Этот тариф недоступен для покупки"})

    price = price_for(plan, period)
    if current_code == "free":
        return Quote(action="pay", kind="initial", price=price, amount=price), plan, sub

    current = await get_plan(db, current_code)
    same = current.code == plan.code and sub.period == period
    if same:
        if sub.cancel_at_period_end or sub.pending_plan_code:
            return Quote(action="resume"), plan, sub
        raise HTTPException(400, detail={"code": "same_plan", "message": "Этот тариф уже активен"})

    is_upgrade = plan.sort_order > current.sort_order or (
        plan.code == current.code and sub.period == "month" and period == "year"
    )
    if not is_upgrade:
        return Quote(action="schedule", price=price), plan, sub

    credit = _credit(sub, now)
    amount = max(price - credit, 100)           # минимум 1 ₽ (ограничение платёжных систем)
    return Quote(action="pay", kind="upgrade", price=price, credit=credit, amount=amount), plan, sub


async def start_checkout(db: AsyncSession, user: User, plan_code: str, period: str, provider_name: Optional[str] = None) -> dict:
    quote, plan, sub = await make_quote(db, user, plan_code, period)

    if quote.action == "cancel":
        sub.cancel_at_period_end = True
        sub.pending_plan_code = None
        sub.pending_period = None
        await db.commit()
        return {"action": "cancel", "effective_at": sub.current_period_end}
    if quote.action == "schedule":
        sub.pending_plan_code = plan.code
        sub.pending_period = period
        sub.cancel_at_period_end = False
        await db.commit()
        return {"action": "scheduled", "effective_at": sub.current_period_end, "plan_code": plan.code, "period": period}
    if quote.action == "resume":
        sub.cancel_at_period_end = False
        sub.pending_plan_code = None
        sub.pending_period = None
        await db.commit()
        return {"action": "resumed"}

    provider = get_provider(provider_name)

    # Не плодим pending-платежи: переиспользуем незавершённый платёж по тому же тарифу/периоду
    existing = (await db.execute(
        select(Payment).where(
            Payment.user_id == user.id,
            Payment.plan_code == plan.code,
            Payment.period == period,
            Payment.status.in_(("pending", "requires_action")),
        ).order_by(Payment.id.desc())
    )).scalars().first()
    if existing is not None:
        existing.amount = quote.amount
        existing.plan_price = quote.price
        existing.kind = quote.kind
        existing.meta = {**(existing.meta or {}), "credit": quote.credit}
        await db.commit()
        await db.refresh(existing)
        return {"action": "pay", "payment": payment_dto(existing)}

    payment = Payment(
        user_id=user.id, provider=provider.name, plan_code=plan.code, period=period, kind=quote.kind,
        amount=quote.amount, plan_price=quote.price, status="pending", idempotency_key=uuid.uuid4().hex,
        meta={"credit": quote.credit},
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    return_url = f"{settings.app_url}/billing/return?payment={payment.id}"
    try:
        result = await provider.create_payment(payment=payment, user=user, description=describe(plan, period), return_url=return_url)
    except Exception as e:
        payment.status = "failed"
        payment.failure_reason = f"Не удалось создать платёж: {e}"[:250]
        await db.commit()
        raise HTTPException(502, detail={"code": "payment_provider_error", "message": "Платёжный сервис временно недоступен"})
    await apply_result(db, payment, result)
    return {"action": "pay", "payment": payment_dto(payment)}


async def apply_result(db: AsyncSession, payment: Payment, result: PaymentResult, renewal: bool = False) -> None:
    """Применяет результат от провайдера к платежу (идемпотентно)."""
    if result.provider_payment_id:
        payment.provider_payment_id = result.provider_payment_id
    if result.confirmation_url:
        payment.confirmation_url = result.confirmation_url
    if payment.status == "succeeded":
        await db.commit()
        return
    if result.status == "succeeded":
        await finalize_success(db, payment, result.payment_method_id, result.payment_method_label, renewal=renewal)
    elif result.status in ("failed", "canceled"):
        payment.status = "failed"
        payment.failure_reason = result.failure_reason or "Платёж не прошёл"
        await db.commit()
    else:
        payment.status = result.status if result.status in ("pending", "requires_action") else "pending"
        await db.commit()


async def finalize_success(db: AsyncSession, payment: Payment, method_id: Optional[str], method_label: Optional[str], renewal: bool = False) -> None:
    if payment.status == "succeeded":
        return
    now = utcnow()
    payment.status = "succeeded"
    payment.paid_at = now
    payment.failure_reason = None

    sub = (await db.execute(select(Subscription).where(Subscription.user_id == payment.user_id))).scalar_one_or_none()
    if sub is None:
        await db.commit()
        return
    start = now
    if renewal and sub.current_period_end:
        start = sub.current_period_end
    sub.plan_code = payment.plan_code
    sub.period = payment.period
    sub.current_period_start = start
    sub.current_period_end = add_period(start, payment.period)
    sub.amount_paid = payment.plan_price
    sub.status = "active"
    sub.cancel_at_period_end = False
    sub.pending_plan_code = None
    sub.pending_period = None
    sub.renewal_attempts = 0
    sub.next_retry_at = None
    sub.provider = payment.provider
    if method_id:
        sub.payment_method_id = method_id
        sub.payment_method_label = method_label
    await db.commit()


async def downgrade_to_free(db: AsyncSession, sub: Subscription) -> None:
    sub.plan_code = "free"
    sub.period = None
    sub.status = "active"
    sub.current_period_start = None
    sub.current_period_end = None
    sub.amount_paid = 0
    sub.cancel_at_period_end = False
    sub.pending_plan_code = None
    sub.pending_period = None
    sub.payment_method_id = None
    sub.payment_method_label = None
    sub.renewal_attempts = 0
    sub.next_retry_at = None
    await db.commit()


async def _handle_renewal_failure(db: AsyncSession, sub: Subscription, now: datetime) -> None:
    sub.status = "past_due"
    sub.renewal_attempts = (sub.renewal_attempts or 0) + 1
    end = sub.current_period_end or now
    if sub.renewal_attempts >= MAX_RENEWAL_ATTEMPTS or now >= end + timedelta(days=GRACE_DAYS):
        await downgrade_to_free(db, sub)
        return
    sub.next_retry_at = now + timedelta(days=1)
    await db.commit()


async def renew_one(db: AsyncSession, sub: Subscription, now: datetime) -> str:
    """→ 'downgraded' | 'renewed' | 'failed' | 'pending' | 'skipped'"""
    if sub.provider == "manual" or sub.cancel_at_period_end and not sub.pending_plan_code:
        await downgrade_to_free(db, sub)
        return "downgraded"
    target_code = sub.pending_plan_code or sub.plan_code
    target_period = sub.pending_period or sub.period
    if target_code in ("free", "local") or not target_period:
        await downgrade_to_free(db, sub)
        return "downgraded"

    # не создаём второй платёж, пока предыдущий автоплатёж ещё обрабатывается
    recent = (await db.execute(
        select(Payment).where(Payment.user_id == sub.user_id, Payment.kind == "renewal", Payment.status == "pending",
                              Payment.created_at > now - timedelta(days=1))
    )).scalars().first()
    if recent:
        return "skipped"

    user = await db.get(User, sub.user_id)
    plan = await get_plan(db, target_code)
    price = price_for(plan, target_period)
    if not sub.payment_method_id or user is None:
        await _handle_renewal_failure(db, sub, now)
        return "failed"

    provider = get_provider(sub.provider)
    payment = Payment(
        user_id=sub.user_id, provider=provider.name, plan_code=plan.code, period=target_period, kind="renewal",
        amount=price, plan_price=price, status="pending", idempotency_key=uuid.uuid4().hex, meta={},
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    try:
        result = await provider.charge_saved(payment=payment, user=user, payment_method_id=sub.payment_method_id,
                                             description=describe(plan, target_period))
    except Exception as e:
        payment.status = "failed"
        payment.failure_reason = str(e)[:250]
        await db.commit()
        await _handle_renewal_failure(db, sub, now)
        return "failed"

    await apply_result(db, payment, result, renewal=True)
    if payment.status == "succeeded":
        return "renewed"
    if payment.status == "failed":
        await _handle_renewal_failure(db, sub, now)
        return "failed"
    return "pending"


async def process_renewals(db: AsyncSession, now: Optional[datetime] = None, user_id: Optional[int] = None) -> dict[str, int]:
    now = now or utcnow()
    q = select(Subscription).where(
        Subscription.plan_code.notin_(["free", "local"]),
        Subscription.current_period_end.is_not(None),
        Subscription.current_period_end <= now,
    )
    if user_id is not None:
        q = q.where(Subscription.user_id == user_id)
    stats: dict[str, int] = {}
    for sub in (await db.execute(q)).scalars().all():
        if sub.next_retry_at and sub.next_retry_at > now and user_id is None:
            continue
        outcome = await renew_one(db, sub, now)
        stats[outcome] = stats.get(outcome, 0) + 1
    return stats


async def grant_subscription(db: AsyncSession, user: User, plan_code: str, period: str, days: Optional[int] = None) -> Subscription:
    """Ручная выдача тарифа администратором (без платежа)."""
    sub = await get_subscription(db, user)
    now = utcnow()
    if plan_code == "free":
        await downgrade_to_free(db, sub)
        return sub
    sub.plan_code = plan_code
    sub.period = period
    sub.status = "active"
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=days) if days else add_period(now, period)
    sub.amount_paid = 0
    sub.cancel_at_period_end = False
    sub.pending_plan_code = None
    sub.pending_period = None
    sub.provider = "manual"
    sub.payment_method_id = None
    sub.payment_method_label = None
    await db.commit()
    return sub
