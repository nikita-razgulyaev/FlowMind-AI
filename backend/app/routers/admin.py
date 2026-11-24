from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..services.llm import provider_status as llm_provider_status
from ..database import get_db
from ..deps import require_admin
from ..models import AuditLog, Execution, Feedback, Payment, Plan, Subscription, User, Workflow, utcnow
from ..services import billing
from ..services.feedback import STATUSES as FEEDBACK_STATUSES, TYPES as FEEDBACK_TYPES, feedback_csv, forward_to_formspree
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
        "feedback_new": (await db.execute(select(func.count()).select_from(Feedback).where(Feedback.status == "new"))).scalar_one(),
        "workflows_total": (await db.execute(select(func.count()).select_from(Workflow))).scalar_one(),
        "executions_total": (await db.execute(select(func.count()).select_from(Execution))).scalar_one(),
        "runs_by_day": [{"date": d, **v} for d, v in days.items()],
        "ai": {
            "enabled": bool(await get_app_setting(db, "ai_enabled", True)),
            "daily_cap": int(await get_app_setting(db, "ai_daily_cap", settings.ai_daily_cap)),
            "calls_today": await get_global(db, "platform_ai_calls"),
            "key_configured": settings.platform_llm_configured,
            "fallback_models": max(len(settings.platform_llm_providers) - 1, 0),
            "models": llm_provider_status(),
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


# ───────────────────────── обратная связь ─────────────────────────

def feedback_dto(f: Feedback) -> dict:
    return {"id": f.id, "created_at": f.created_at, "status": f.status, "type": f.type, "name": f.name, "email": f.email,
            "plan": f.plan, "user_id": f.user_id, "message": f.message, "page": f.page, "user_agent": f.user_agent,
            "spam_reason": f.spam_reason, "admin_note": f.admin_note or "", "forward_status": f.forward_status}


def _feedback_filter(status: str, type_: str, q: str):
    """По умолчанию (status пуст) спам не показываем — он в отдельной вкладке."""
    conditions = [Feedback.status == status] if status else [Feedback.status != "spam"]
    if type_:
        conditions.append(Feedback.type == type_)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        conditions.append(or_(func.lower(Feedback.message).like(like), func.lower(Feedback.email).like(like),
                              func.lower(Feedback.name).like(like)))
    return conditions


def _check_feedback_filters(status: str, type_: str) -> None:
    if status and status not in FEEDBACK_STATUSES:
        raise HTTPException(400, detail={"code": "bad_status", "message": "Неизвестный статус"})
    if type_ and type_ not in FEEDBACK_TYPES:
        raise HTTPException(400, detail={"code": "bad_type", "message": "Неизвестный тип обращения"})


@router.get("/feedback")
async def admin_feedback(status: str = "", type: str = "", q: str = "", limit: int = 25, offset: int = 0,
                         admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    _check_feedback_filters(status, type)
    limit = max(1, min(limit, 100))
    conditions = _feedback_filter(status, type, q)
    total = (await db.execute(select(func.count()).select_from(Feedback).where(*conditions))).scalar_one()
    rows = (await db.execute(select(Feedback).where(*conditions).order_by(Feedback.id.desc()).limit(limit).offset(max(0, offset)))).scalars().all()
    counts = {k: 0 for k in FEEDBACK_STATUSES}
    for key, n in (await db.execute(select(Feedback.status, func.count()).group_by(Feedback.status))).all():
        counts[key] = n
    return {"total": total, "items": [feedback_dto(f) for f in rows], "counts": counts}


@router.get("/feedback/export.csv")
async def admin_feedback_csv(status: str = "", type: str = "", q: str = "", admin: User = Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    _check_feedback_filters(status, type)
    rows = (await db.execute(select(Feedback).where(*_feedback_filter(status, type, q)).order_by(Feedback.id.desc()).limit(10_000))).scalars().all()
    filename = f"feedback-{utcnow().strftime('%Y-%m-%d')}.csv"
    return Response(feedback_csv(rows), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


class FeedbackPatch(BaseModel):
    status: Optional[str] = None
    admin_note: Optional[str] = Field(default=None, max_length=2000)


@router.patch("/feedback/{feedback_id}")
async def admin_feedback_update(feedback_id: int, data: FeedbackPatch, background: BackgroundTasks,
                                admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    f = await db.get(Feedback, feedback_id)
    if not f:
        raise HTTPException(404, "Not found")
    if data.status is not None and data.status not in FEEDBACK_STATUSES:
        raise HTTPException(400, detail={"code": "bad_status", "message": "Неизвестный статус"})
    forward = False
    if data.status is not None:
        # «Это не спам»: обращение, которое не успело уйти в Formspree, отправляем сейчас
        forward = f.status == "spam" and data.status != "spam" and f.forward_status == "off" and bool(settings.formspree_endpoint)
        f.status = data.status
    if data.admin_note is not None:
        f.admin_note = data.admin_note.strip()
    if forward:
        f.forward_status = "pending"
    await db.commit()
    if forward:
        background.add_task(forward_to_formspree, f.id)
    return feedback_dto(f)


@router.post("/feedback/{feedback_id}/forward")
async def admin_feedback_forward(feedback_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    f = await db.get(Feedback, feedback_id)
    if not f:
        raise HTTPException(404, "Not found")
    if not settings.formspree_endpoint:
        raise HTTPException(400, detail={"code": "formspree_off", "message": "Пересылка не настроена: задайте FORMSPREE_URL"})
    if f.status == "spam":
        raise HTTPException(400, detail={"code": "is_spam", "message": "Сначала верните обращение из спама"})
    await forward_to_formspree(f.id)
    await db.refresh(f)
    return {"forward_status": f.forward_status}


@router.delete("/feedback/{feedback_id}")
async def admin_feedback_delete(feedback_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    f = await db.get(Feedback, feedback_id)
    if not f:
        raise HTTPException(404, "Not found")
    await db.delete(f)
    await db.commit()
    await audit(db, admin, "feedback.delete", str(feedback_id))
    return {"ok": True}


@router.delete("/feedback")
async def admin_feedback_clear_spam(status: str = "", admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Массово удаляет только спам — другие статусы так удалить нельзя."""
    if status != "spam":
        raise HTTPException(400, detail={"code": "only_spam", "message": "Массово можно удалить только спам (status=spam)"})
    result = await db.execute(delete(Feedback).where(Feedback.status == "spam"))
    await db.commit()
    await audit(db, admin, "feedback.clear_spam", "", {"deleted": result.rowcount})
    return {"deleted": result.rowcount}
