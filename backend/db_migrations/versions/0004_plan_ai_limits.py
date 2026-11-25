"""новые лимиты AI в тарифах (50/1000/2800 запусков, 25/150/600 сообщений чата)

Меняет только те тарифы, у которых значения всё ещё стандартные старые:
правки администратора в админ-панели не перезаписываются.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import json
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

# code: (старые запуски, старые сообщения чата, новые запуски, новые сообщения чата, старый текст, новый текст)
CHANGES = {
    "free": (300, 100, 50, 25, "300 AI-запусков в месяц", "50 AI-запусков в месяц"),
    "pro": (3000, 1500, 1000, 150, "3 000 AI-запусков в месяц", "1 000 AI-запусков в месяц"),
    "business": (20000, 10000, 2800, 600, "20 000 AI-запусков в месяц", "2 800 AI-запусков в месяц"),
}


def _apply(old_idx: int, new_idx: int) -> None:
    plans = sa.table("plans", sa.column("code", sa.String), sa.column("ai_runs_month", sa.Integer),
                     sa.column("ai_chat_messages_month", sa.Integer), sa.column("features", sa.JSON))
    bind = op.get_bind()
    for code, spec in CHANGES.items():
        old_runs, old_chat, new_runs, new_chat = (spec[old_idx * 2], spec[old_idx * 2 + 1],
                                                  spec[new_idx * 2], spec[new_idx * 2 + 1])
        old_text, new_text = (spec[4], spec[5]) if new_idx == 1 else (spec[5], spec[4])
        bind.execute(plans.update().where(plans.c.code == code, plans.c.ai_runs_month == old_runs)
                     .values(ai_runs_month=new_runs))
        bind.execute(plans.update().where(plans.c.code == code, plans.c.ai_chat_messages_month == old_chat)
                     .values(ai_chat_messages_month=new_chat))
        row = bind.execute(sa.select(plans.c.features).where(plans.c.code == code)).first()
        features = row[0] if row else None
        if isinstance(features, str):
            features = json.loads(features)
        if isinstance(features, list) and old_text in features:
            features = [new_text if item == old_text else item for item in features]
            bind.execute(plans.update().where(plans.c.code == code).values(features=features))


def upgrade() -> None:
    _apply(0, 1)


def downgrade() -> None:
    _apply(1, 0)
