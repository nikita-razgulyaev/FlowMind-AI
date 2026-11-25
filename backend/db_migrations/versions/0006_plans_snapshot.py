"""снимок «прежних значений из кода» для синхронизации тарифов с plans_config.py

Сервис при старте обновляет поле тарифа из plans_config.py, только если в базе оно всё ещё равно
прежнему значению из кода (иначе это ручная правка из админ-панели). Прежние значения хранятся в
app_settings под ключом plans_defaults_applied. Эта миграция записывает туда значения, которые
были в коде до появления plans_config.py и до последнего пересчёта тарифов (состояние после 0005),
чтобы первый же запуск новой версии подтянул изменения. Если снимок уже есть, ничего не меняется.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

KEY = "plans_defaults_applied"

SNAPSHOT = {
    "free": dict(
        name="Бесплатно", description="Чтобы попробовать сервис", price_month=0, price_year=0, sort_order=0, is_public=True,
        max_ai_workflows=5, max_regular_workflows=20, ai_runs_month=50, regular_runs_month=3000,
        telegram_triggers=1, history_days=14, ai_chat_messages_month=25,
        features=["5 AI-воркфлоу и 20 обычных", "50 AI-запусков в месяц", "3 000 обычных запусков", "1 Telegram-триггер",
                  "AI-ассистент для сборки графа", "История выполнений 14 дней"]),
    "pro": dict(
        name="Про", description="Для малого бизнеса и фрилансеров", price_month=99000, price_year=950400, sort_order=1,
        is_public=True, max_ai_workflows=15, max_regular_workflows=100, ai_runs_month=1000, regular_runs_month=30000,
        telegram_triggers=3, history_days=60, ai_chat_messages_month=150,
        features=["15 AI-воркфлоу и 100 обычных", "1 000 AI-запусков в месяц", "30 000 обычных запусков", "3 Telegram-триггера",
                  "Свои API-ключи (OpenAI, Groq, HF и др.)", "История выполнений 60 дней"]),
    "business": dict(
        name="Бизнес", description="Для команд и серьёзной нагрузки", price_month=299000, price_year=2870400, sort_order=2,
        is_public=True, max_ai_workflows=40, max_regular_workflows=None, ai_runs_month=2800, regular_runs_month=200000,
        telegram_triggers=10, history_days=180, ai_chat_messages_month=600,
        features=["40 AI-воркфлоу, обычные без лимита", "2 800 AI-запусков в месяц", "200 000 обычных запусков",
                  "10 Telegram-триггеров", "Приоритетная поддержка", "История выполнений 180 дней"]),
    "local": dict(name="Локальный", description="Self-hosted: без ограничений", price_month=0, price_year=0,
                  sort_order=99, is_public=False, features=[]),
}


def upgrade() -> None:
    settings = sa.table("app_settings", sa.column("key", sa.String), sa.column("value", sa.JSON))
    bind = op.get_bind()
    exists = bind.execute(sa.select(settings.c.key).where(settings.c.key == KEY)).first()
    if exists is None:
        bind.execute(settings.insert().values(key=KEY, value=SNAPSHOT))


def downgrade() -> None:
    pass        # снимок безвреден: используется только кодом, который его понимает
