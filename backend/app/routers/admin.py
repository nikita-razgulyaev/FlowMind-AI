from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import require_admin
from ..models import AuditLog, Execution, Payment, Plan, Subscription, User, Workflow, utcnow
from ..services import billing
from ..services.limits import (count_workflows, effective_plan_code, get_global, get_subscription, get_usage,
                               get_user_plan)
from ..services.platform_ai import get_app_setting, set_app_setting
from .auth import user_dto
from .dto import plan_dto, subscription_dto

router = APIRouter(prefix="/admin", tags=["admin"])


async def audit(db: AsyncSession, admin: User, action: str, target: str = "", details: Optional[dict] = None) -> None:
    db.add(AuditLog(admin_id=admin.id, admin_email=admin.email, action=action, target=target, details=details or {}))
    await db.commit()


@router.get("/stats")
async def stats(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    now = utcnow()
    week = now - timedelta(days=7)
    users_total = (await db.execute(select(func.count()).select_from(User).where(User.is_local.is_(False)))).scalar_one()
    users_new = (await db.execute(select(func.count()).select_from(User).where(User.created_at >= week, User.is_local.is_(False)))).scalar_one()

    plans = {p.code: p for p in (await db.execute(select(Plan))).scalars().all()}
    paid = {"pro": 0, "business": 0}
    mrr = 0
    for sub in (await db.execute(select(Subscription).where(Subscription.plan_code.in_(["pro", "business"])))).scalars().all():
        if effective_plan_code(sub, now) != sub.plan_code:
            continue
        paid[sub.plan_code] += 1
        plan = plans[sub.plan_code]
        mrr += plan.price_month if sub.period == "month" else plan.price_year // 12

    revenue_total = (await db.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "succeeded"))).scalar_one()
    revenue_30d = (await db.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.status == "succeeded", Payment.paid_at >= now - timedelta(days=30)))).scalar_one()

    since = (now - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (await db.execute(select(Execution.started_at, Execution.is_ai).where(Execution.started_at >= since))).all()
    days = {(since + timedelta(days=i)).strftime("%Y-%m-%d"): {"ai": 0, "regular": 0} for i in range(14)}
    for started, is_ai in rows:
        key = started.strftime("%Y-%m-%d")
        if key in days:
            days[key]["ai" if is_ai else "regular"] += 1

    return {
        "users_total": users_total, "users_new_7d": users_new, "paid_subscriptions": paid,
        "mrr": mrr, "revenue_total": revenue_total, "revenue_30d": revenue_30d,
        "workflows_total": (await db.execute(select(func.count()).select_from(Workflow))).scalar_one(),
        "executions_total": (await db.execute(select(func.count()).select_from(Execution))).scalar_one(),
        "runs_by_day": [{"date": d, **v} for d, v in days.items()],
        "ai": {
            "enabled": bool(await get_app_setting(db, "ai_enabled", True)),
            "daily_cap": int(await get_app_setting(db, "ai_daily_cap", settings.ai_daily_cap)),
            "calls_today": await get_global(db, "platform_ai_calls"),
            "key_configured": bool(settings.platform_llm_api_key),
        },
    }


@router.get("/users")
async def list_users(q: str = "", limit: int = 50, offset: int = 0, admin: User = Depends(require_admin),
                     db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 200))
    query = select(User).where(User.is_local.is_(False))
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(User.email).like(like), func.lower(User.name).like(like)))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    users = (await db.execute(query.order_by(User.id.desc()).limit(limit).offset(offset))).scalars().all()
    items = []
    for u in users:
        sub = await get_subscription(db, u)
        items.append({**user_dto(u), "is_active": u.is_active, "last_login_at": u.last_login_at,
                      "plan": effective_plan_code(sub), "period": sub.period, "plan_until": sub.current_period_end})
    return {"total": total, "items": items}


@router.get("/users/{user_id}")
async def user_detail(user_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    u = await db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    sub = await get_subscription(db, u)
    payments = (await db.execute(select(Payment).where(Payment.user_id == u.id).order_by(Payment.id.desc()).limit(20))).scalars().all()
    wfs = (await db.execute(select(Workflow).where(Workflow.user_id == u.id).order_by(Workflow.id.desc()).limit(50))).scalars().all()
    return {
        "user": {**user_dto(u), "is_active": u.is_active, "last_login_at": u.last_login_at},
        "subscription": subscription_dto(sub),
        "plan": plan_dto(await get_user_plan(db, u)),
        "usage": await get_usage(db, u.id),
        "workflows_count": await count_workflows(db, u.id),
        "workflows": [{"id": w.id, "name": w.name, "is_ai": w.is_ai, "is_active": w.is_active, "created_at": w.created_at} for w in wfs],
        "payments": [billing.payment_dto(p) for p in payments],
    }


class UserPatch(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = Field(default=None, pattern="^(user|admin)$")
    name: Optional[str] = Field(default=None, max_length=120)


@router.patch("/users/{user_id}")
async def patch_user(user_id: int, data: UserPatch, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    u = await db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id and (data.is_active is False or data.role == "user"):
        raise HTTPException(400, detail={"code": "self_lockout", "message": "Нельзя заблокировать или разжаловать самого себя"})
    changes = data.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(u, key, value)
    await db.commit()
    await audit(db, admin, "user.update", u.email, changes)
    return {**user_dto(u), "is_active": u.is_active}


class GrantIn(BaseModel):
    plan_code: str
    period: str = Field("month", pattern="^(month|year)$")
    days: Optional[int] = Field(default=None, ge=1, le=3650)


@router.post("/users/{user_id}/grant")
async def grant(user_id: int, data: GrantIn, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    u = await db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    plan = (await db.execute(select(Plan).where(Plan.code == data.plan_code))).scalar_one_or_none()
    if not plan or plan.code == "local":
        raise HTTPException(400, detail={"code": "bad_plan", "message": "Неизвестный тариф"})
    sub = await billing.grant_subscription(db, u, data.plan_code, data.period, data.days)
    await audit(db, admin, "subscription.grant", u.email, data.model_dump())
    return subscription_dto(sub)


@router.get("/plans")
async def admin_plans(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return [plan_dto(p) for p in (await db.execute(select(Plan).order_by(Plan.sort_order))).scalars().all()]


class PlanPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=60)
    description: Optional[str] = Field(default=None, max_length=255)
    price_month: Optional[int] = Field(default=None, ge=0)
    price_year: Optional[int] = Field(default=None, ge=0)
    features: Optional[list[str]] = None
    # None в лимитах означает «без ограничений», поэтому передаём их отдельным объектом
    limits: Optional[dict] = None


LIMIT_FIELDS = {
    "ai_workflows": "max_ai_workflows", "regular_workflows": "max_regular_workflows", "ai_run": "ai_runs_month",
    "regular_run": "regular_runs_month", "telegram_triggers": "telegram_triggers", "history_days": "history_days",
    "ai_chat": "ai_chat_messages_month",
}


@router.put("/plans/{code}")
async def update_plan(code: str, data: PlanPatch, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    plan = (await db.execute(select(Plan).where(Plan.code == code))).scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    for field in ("name", "description", "price_month", "price_year", "features"):
        value = getattr(data, field)
        if value is not None:
            setattr(plan, field, value)
    for key, value in (data.limits or {}).items():
        if key in LIMIT_FIELDS:
            if value is not None and (not isinstance(value, int) or value < 0):
                raise HTTPException(400, detail={"code": "bad_limit", "message": f"Некорректный лимит: {key}"})
            setattr(plan, LIMIT_FIELDS[key], value)
    await db.commit()
    await audit(db, admin, "plan.update", code, data.model_dump(exclude_none=True))
    return plan_dto(plan)


@router.get("/payments")
async def admin_payments(status: str = "", limit: int = 100, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    q = select(Payment, User.email).outerjoin(User, User.id == Payment.user_id).order_by(Payment.id.desc()).limit(max(1, min(limit, 500)))
    if status:
        q = q.where(Payment.status == status)
    return [{**billing.payment_dto(p), "user_email": email} for p, email in (await db.execute(q)).all()]


class SettingsIn(BaseModel):
    ai_enabled: Optional[bool] = None
    ai_daily_cap: Optional[int] = Field(default=None, ge=0, le=10_000_000)


@router.get("/settings")
async def get_admin_settings(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return {"ai_enabled": bool(await get_app_setting(db, "ai_enabled", True)),
            "ai_daily_cap": int(await get_app_setting(db, "ai_daily_cap", settings.ai_daily_cap))}


@router.put("/settings")
async def put_admin_settings(data: SettingsIn, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    for key, value in data.model_dump(exclude_none=True).items():
        await set_app_setting(db, key, value)
    await audit(db, admin, "settings.update", "", data.model_dump(exclude_none=True))
    return await get_admin_settings(admin, db)


@router.get("/audit")
async def audit_log(limit: int = 100, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500))))).scalars().all()
    return [{"id": r.id, "admin_email": r.admin_email, "action": r.action, "target": r.target,
             "details": r.details, "created_at": r.created_at} for r in rows]
