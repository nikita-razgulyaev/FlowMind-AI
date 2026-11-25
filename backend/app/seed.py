"""Начальные данные: тарифы, локальный пользователь, администратор. Всё идемпотентно."""
import logging
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .deps import LOCAL_EMAIL
from .models import AppSetting, Connection, Execution, Plan, Subscription, User, Workflow
from .plans_config import LIMIT_FIELDS, plan_rows
from .security import hash_password

log = logging.getLogger("flowmind.seed")

# Тарифы и лимиты задаются в одном месте: app/plans_config.py
DEFAULT_PLANS = plan_rows()

PLANS_SNAPSHOT_KEY = "plans_defaults_applied"
SYNC_FIELDS = ("name", "description", "price_month", "price_year", "sort_order", "is_public", "features",
               *LIMIT_FIELDS)


async def sync_plans(db: AsyncSession, rows: Optional[list] = None, force: Optional[bool] = None) -> None:
    """Приводит таблицу plans в соответствие с plans_config.py.

    * Новых тарифов добавляет.
    * В существующих поле обновляется, только если в базе оно всё ещё равно прежнему значению из кода
      (запомненному при прошлом старте): ручные правки администратора не затираются.
    * force=True (PLANS_FORCE_SYNC=true) перезаписывает все поля значениями из кода.
    """
    rows = DEFAULT_PLANS if rows is None else rows
    force = settings.plans_force_sync if force is None else force
    existing = {p.code: p for p in (await db.execute(select(Plan))).scalars()}
    snapshot_row = (await db.execute(select(AppSetting).where(AppSetting.key == PLANS_SNAPSHOT_KEY))).scalar_one_or_none()
    snapshot = snapshot_row.value if snapshot_row is not None and isinstance(snapshot_row.value, dict) else {}

    for spec in rows:
        plan = existing.get(spec["code"])
        if plan is None:
            db.add(Plan(**spec))
            continue
        previous = snapshot.get(spec["code"])
        for field in SYNC_FIELDS:
            if field not in spec:
                continue
            if force:
                setattr(plan, field, spec[field])
            elif previous is not None and field in previous and spec[field] != previous[field] \
                    and getattr(plan, field) == previous[field]:
                setattr(plan, field, spec[field])
                log.info("Тариф %s: %s обновлён из plans_config.py (%r → %r)", spec["code"], field, previous[field], spec[field])

    new_snapshot = {spec["code"]: {f: spec[f] for f in SYNC_FIELDS if f in spec} for spec in rows}
    if snapshot_row is None:
        db.add(AppSetting(key=PLANS_SNAPSHOT_KEY, value=new_snapshot))
    else:
        snapshot_row.value = new_snapshot
    await db.commit()


async def seed_plans(db: AsyncSession) -> None:
    await sync_plans(db)


async def ensure_subscription(db: AsyncSession, user: User) -> None:
    sub = (await db.execute(select(Subscription).where(Subscription.user_id == user.id))).scalar_one_or_none()
    if sub is None:
        db.add(Subscription(user_id=user.id, plan_code="local" if user.is_local else "free"))
        await db.commit()


async def seed_local_user(db: AsyncSession) -> User:
    user = (await db.execute(select(User).where(User.email == LOCAL_EMAIL))).scalar_one_or_none()
    if user is None:
        user = User(email=LOCAL_EMAIL, name="Локальный пользователь", role="admin", is_local=True,
                    email_verified=True, is_active=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    await ensure_subscription(db, user)
    # данные, созданные до появления пользователей (старые установки), переходят локальному пользователю
    for model in (Workflow, Execution, Connection):
        await db.execute(update(model).where(model.user_id.is_(None)).values(user_id=user.id))
    await db.commit()
    return user


async def seed_admin(db: AsyncSession) -> None:
    email = settings.admin_email.strip().lower()
    if not email:
        return
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        if not settings.admin_password:
            return                                          # администратором станет аккаунт с этим email при регистрации
        user = User(email=email, name="Администратор", role="admin", email_verified=True,
                    password_hash=hash_password(settings.admin_password))
        db.add(user)
        await db.commit()
        await db.refresh(user)
        log.info("Создан администратор %s", email)
    elif user.role != "admin":
        user.role = "admin"
        await db.commit()
    await ensure_subscription(db, user)


async def run_seed(db: AsyncSession) -> None:
    await seed_plans(db)
    if settings.is_local or not settings.auth_required:
        await seed_local_user(db)
    await seed_admin(db)
