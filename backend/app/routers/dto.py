from ..models import Plan, Subscription
from ..services.limits import effective_plan_code, plan_limits


def plan_dto(p: Plan) -> dict:
    return {
        "code": p.code, "name": p.name, "description": p.description, "currency": p.currency,
        "price_month": p.price_month, "price_year": p.price_year, "features": p.features or [],
        "sort_order": p.sort_order, "is_public": p.is_public, "limits": plan_limits(p),
    }


def subscription_dto(sub: Subscription) -> dict:
    return {
        "plan_code": sub.plan_code, "effective_plan": effective_plan_code(sub), "period": sub.period,
        "status": sub.status, "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end, "cancel_at_period_end": sub.cancel_at_period_end,
        "pending_plan_code": sub.pending_plan_code, "pending_period": sub.pending_period,
        "payment_method_label": sub.payment_method_label, "provider": sub.provider,
        "amount_paid": sub.amount_paid,
    }
