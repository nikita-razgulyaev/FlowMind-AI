"""лимиты AI-воркфлоу и Telegram-триггеров под новые AI-квоты (Про 15/3, Бизнес 40/10)

Как и в 0004, меняются только стандартные старые значения: правки администратора сохраняются.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import json
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

# code: (колонка, старое, новое)
VALUES = {
    "pro": [("max_ai_workflows", 25, 15), ("telegram_triggers", 5, 3)],
    "business": [("max_ai_workflows", 100, 40), ("telegram_triggers", 20, 10)],
}
# code: (старый текст, новый текст)
TEXTS = {
    "pro": [("25 AI-воркфлоу и 100 обычных", "15 AI-воркфлоу и 100 обычных"),
            ("5 Telegram-триггеров", "3 Telegram-триггера")],
    "business": [("100 AI-воркфлоу, обычные без лимита", "40 AI-воркфлоу, обычные без лимита"),
                 ("20 Telegram-триггеров", "10 Telegram-триггеров")],
}


def _apply(forward: bool) -> None:
    plans = sa.table("plans", sa.column("code", sa.String), sa.column("max_ai_workflows", sa.Integer),
                     sa.column("telegram_triggers", sa.Integer), sa.column("features", sa.JSON))
    bind = op.get_bind()
    for code, items in VALUES.items():
        for column, old, new in items:
            src, dst = (old, new) if forward else (new, old)
            bind.execute(plans.update().where(plans.c.code == code, plans.c[column] == src).values({column: dst}))
        row = bind.execute(sa.select(plans.c.features).where(plans.c.code == code)).first()
        features = row[0] if row else None
        if isinstance(features, str):
            features = json.loads(features)
        if isinstance(features, list):
            for old_text, new_text in TEXTS[code]:
                src, dst = (old_text, new_text) if forward else (new_text, old_text)
                features = [dst if item == src else item for item in features]
            bind.execute(plans.update().where(plans.c.code == code).values(features=features))


def upgrade() -> None:
    _apply(True)


def downgrade() -> None:
    _apply(False)
