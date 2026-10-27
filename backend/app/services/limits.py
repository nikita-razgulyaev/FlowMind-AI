"""Тарифы, подписка пользователя, счётчики использования и проверка лимитов."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GlobalCounter, Plan, Subscription, UsageCounter, User, Workflow, utcnow

AI_NODE_TYPES = {"llm", "agent"}
GRACE_DAYS = 3

KIND_LABELS = {
    "ai_workflows": "AI-воркфлоу",
    "regular_workflows": "обычных воркфлоу",
    "ai_run": "AI-запусков в месяц",
    "regular_run": "обычных запусков в месяц",
    "telegram_triggers": "активных Telegram-триггеров",
    "ai_chat": "сообщений AI-чата в месяц",
}


def workflow_flags(nodes: list[dict]) -> tuple[bool, bool]:
    types = {n.get("type") for n in nodes}
    return bool(types & AI_NODE_TYPES), "telegram_trigger" in types


def month_key(now: Optional[datetime] = None) -> str:
    return (now or utcnow()).strftime("%Y-%m")


def day_key(now: Optional[datetime] = None) -> str:
    return (now or utcnow()).strftime("%Y-%m-%d")


class QuotaError(HTTPException):
    def __init__(self, kind: str, limit: int, message: Optional[str] = None):
        super().__init__(
            status_code=402,
            detail={
                "code": "quota_exceeded",
                "kind": kind,
                "limit": limit,
                "message": message or f"Достигнут лимит тарифа: {limit} {KIND_LABELS.get(kind, kind)}. Перейдите на более высокий тариф.",
            },
        )


# ───────────── подписка и план ─────────────

async def get_subscription(db: AsyncSession, user: User) -> Subscription:
    sub = (await db.execute(select(Subscription).where(Subscription.user_id == user.id))).scalar_one_or_none()
    if sub is None:
        sub = Subscription(user_id=user.id, plan_code="local" if user.is_local else "free", status="active")
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
    return sub


def effective_plan_code(sub: Subscription, now: Optional[datetime] = None) -> str:
    now = now or utcnow()
    if sub.plan_code in ("free", "local"):
        return sub.plan_code
    end = sub.current_period_end
    if end is None:
        return sub.plan_code
    if now < end:
        return sub.plan_code
    if sub.status == "past_due" and now < end + timedelta(days=GRACE_DAYS):
        return sub.plan_code
    return "free"


async def get_plan(db: AsyncSession, code: str) -> Plan:
    plan = (await db.execute(select(Plan).where(Plan.code == code))).scalar_one_or_none()
    if plan is None:
        raise HTTPException(500, f"Тариф '{code}' не найден в БД")
    return plan


async def get_user_plan(db: AsyncSession, user: User) -> Plan:
    sub = await get_subscription(db, user)
    return await get_plan(db, effective_plan_code(sub))


# ───────────── счётчики ─────────────

async def _bump(db: AsyncSession, model, filters: dict, by: int = 1) -> None:
    conds = [getattr(model, k) == v for k, v in filters.items()]
    stmt = update(model).where(*conds).values(count=model.count + by)
    res = await db.execute(stmt)
    if res.rowcount == 0:
        try:
            async with db.begin_nested():
                db.add(model(**filters, count=by))
                await db.flush()
        except IntegrityError:
            await db.execute(stmt)
    await db.commit()


async def bump_usage(db: AsyncSession, user_id: int, kind: str, by: int = 1) -> None:
    await _bump(db, UsageCounter, {"user_id": user_id, "period": month_key(), "kind": kind}, by)


async def bump_global(db: AsyncSession, key: str, by: int = 1) -> None:
    await _bump(db, GlobalCounter, {"key": key, "period": day_key()}, by)


async def get_global(db: AsyncSession, key: str, period: Optional[str] = None) -> int:
    row = (await db.execute(
        select(GlobalCounter.count).where(GlobalCounter.key == key, GlobalCounter.period == (period or day_key()))
    )).scalar_one_or_none()
    return row or 0


async def get_usage(db: AsyncSession, user_id: int, period: Optional[str] = None) -> dict[str, int]:
    rows = (await db.execute(
        select(UsageCounter.kind, UsageCounter.count).where(
            UsageCounter.user_id == user_id, UsageCounter.period == (period or month_key())
        )
    )).all()
    usage = {"ai_run": 0, "regular_run": 0, "ai_chat": 0}
    usage.update({k: c for k, c in rows})
    return usage


async def count_workflows(db: AsyncSession, user_id: int) -> dict[str, int]:
    base = select(func.count()).select_from(Workflow).where(Workflow.user_id == user_id)
    ai = (await db.execute(base.where(Workflow.is_ai.is_(True)))).scalar_one()
    regular = (await db.execute(base.where(Workflow.is_ai.is_(False)))).scalar_one()
    tg = (await db.execute(base.where(Workflow.has_telegram_trigger.is_(True), Workflow.is_active.is_(True)))).scalar_one()
    return {"ai_workflows": ai, "regular_workflows": regular, "telegram_triggers": tg}


# ───────────── проверки ─────────────

async def check_workflow_quota(
    db: AsyncSession, user: User, plan: Plan, *, is_ai: bool, has_tg: bool, active: bool,
    exclude_id: Optional[int] = None,
) -> None:
    def base():
        q = select(func.count()).select_from(Workflow).where(Workflow.user_id == user.id)
        if exclude_id is not None:
            q = q.where(Workflow.id != exclude_id)
        return q

    if is_ai and plan.max_ai_workflows is not None:
        n = (await db.execute(base().where(Workflow.is_ai.is_(True)))).scalar_one()
        if n + 1 > plan.max_ai_workflows:
            raise QuotaError("ai_workflows", plan.max_ai_workflows)
    if not is_ai and plan.max_regular_workflows is not None:
        n = (await db.execute(base().where(Workflow.is_ai.is_(False)))).scalar_one()
        if n + 1 > plan.max_regular_workflows:
            raise QuotaError("regular_workflows", plan.max_regular_workflows)
    if has_tg and active and plan.telegram_triggers is not None:
        n = (await db.execute(base().where(Workflow.has_telegram_trigger.is_(True), Workflow.is_active.is_(True)))).scalar_one()
        if n + 1 > plan.telegram_triggers:
            msg = (
                "Telegram-триггеры недоступны на вашем тарифе."
                if plan.telegram_triggers == 0
                else None
            )
            raise QuotaError("telegram_triggers", plan.telegram_triggers, msg)


async def check_and_count_run(db: AsyncSession, user: User, plan: Plan, is_ai: bool) -> None:
    kind = "ai_run" if is_ai else "regular_run"
    limit = plan.ai_runs_month if is_ai else plan.regular_runs_month
    if limit is not None:
        usage = await get_usage(db, user.id)
        if usage[kind] + 1 > limit:
            raise QuotaError(kind, limit)
    await bump_usage(db, user.id, kind)


async def check_chat_quota(db: AsyncSession, user: User, plan: Plan) -> None:
    """Только проверяет лимит; сообщение засчитывается (bump_usage) после успешного ответа модели."""
    limit = plan.ai_chat_messages_month
    if limit is not None:
        usage = await get_usage(db, user.id)
        if usage["ai_chat"] + 1 > limit:
            raise QuotaError("ai_chat", limit)


def plan_limits(plan: Plan) -> dict:
    return {
        "ai_workflows": plan.max_ai_workflows,
        "regular_workflows": plan.max_regular_workflows,
        "ai_run": plan.ai_runs_month,
        "regular_run": plan.regular_runs_month,
        "telegram_triggers": plan.telegram_triggers,
        "history_days": plan.history_days,
        "ai_chat": plan.ai_chat_messages_month,
    }
