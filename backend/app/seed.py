"""Начальные данные: тарифы, локальный пользователь, администратор. Всё идемпотентно."""
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .deps import LOCAL_EMAIL
from .models import Connection, Execution, Plan, Subscription, User, Workflow
from .security import hash_password

log = logging.getLogger("flowmind.seed")

# Цены в копейках. Год = 12 месяцев со скидкой 20%.
DEFAULT_PLANS = [
    dict(code="free", name="Бесплатно", description="Чтобы попробовать сервис", price_month=0, price_year=0, sort_order=0,
         max_ai_workflows=5, max_regular_workflows=20, ai_runs_month=300, regular_runs_month=3000,
         telegram_triggers=1, history_days=14, ai_chat_messages_month=100,
         features=["5 AI-воркфлоу и 20 обычных", "300 AI-запусков в месяц", "3 000 обычных запусков", "1 Telegram-триггер",
                   "AI-ассистент для сборки графа", "История выполнений 14 дней"]),
    dict(code="pro", name="Про", description="Для малого бизнеса и фрилансеров", price_month=99000, price_year=950400, sort_order=1,
         max_ai_workflows=25, max_regular_workflows=100, ai_runs_month=3000, regular_runs_month=30000,
         telegram_triggers=5, history_days=60, ai_chat_messages_month=1500,
         features=["25 AI-воркфлоу и 100 обычных", "3 000 AI-запусков в месяц", "30 000 обычных запусков", "5 Telegram-триггеров",
                   "Свои API-ключи (OpenAI, Groq, HF и др.)", "История выполнений 60 дней"]),
    dict(code="business", name="Бизнес", description="Для команд и серьёзной нагрузки", price_month=299000, price_year=2870400, sort_order=2,
         max_ai_workflows=100, max_regular_workflows=None, ai_runs_month=20000, regular_runs_month=200000,
         telegram_triggers=20, history_days=180, ai_chat_messages_month=10000,
         features=["100 AI-воркфлоу, обычные без лимита", "20 000 AI-запусков в месяц", "200 000 обычных запусков", "20 Telegram-триггеров",
                   "Приоритетная поддержка", "История выполнений 180 дней"]),
    dict(code="local", name="Локальный", description="Self-hosted: без ограничений", price_month=0, price_year=0, sort_order=99,
         is_public=False, features=[]),
]


async def seed_plans(db: AsyncSession) -> None:
    existing = {c for (c,) in (await db.execute(select(Plan.code))).all()}
    for spec in DEFAULT_PLANS:
        if spec["code"] not in existing:                    # правки администратора не перезатираются
            db.add(Plan(**spec))
    await db.commit()


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
