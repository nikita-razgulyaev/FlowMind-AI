"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-23 05:40:32.657634
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


LEGACY_TABLES = ("workflows", "executions", "connections")


def _upgrade_legacy(insp, legacy) -> None:
    """Старые установки (до появления пользователей): добавляем новые колонки к существующим таблицам.
    Строки без user_id при старте получает локальный пользователь (см. app/seed.py)."""
    new_columns = {
        "workflows": [sa.Column("user_id", sa.Integer(), nullable=True),
                      sa.Column("is_ai", sa.Boolean(), nullable=False, server_default=sa.false()),
                      sa.Column("has_telegram_trigger", sa.Boolean(), nullable=False, server_default=sa.false())],
        "executions": [sa.Column("user_id", sa.Integer(), nullable=True),
                       sa.Column("source", sa.String(length=20), nullable=True, server_default="manual"),
                       sa.Column("is_ai", sa.Boolean(), nullable=False, server_default=sa.false())],
        "connections": [sa.Column("user_id", sa.Integer(), nullable=True)],
    }
    for table in legacy:
        existing = {c["name"] for c in insp.get_columns(table)}
        with op.batch_alter_table(table, schema=None) as batch_op:
            for column in new_columns[table]:
                if column.name not in existing:
                    batch_op.add_column(column)
        indexes = {i["name"] for i in insp.get_indexes(table)}
        with op.batch_alter_table(table, schema=None) as batch_op:
            if f"ix_{table}_user_id" not in indexes:
                batch_op.create_index(f"ix_{table}_user_id", ["user_id"], unique=False)
            if table == "executions" and "ix_executions_started_at" not in indexes:
                batch_op.create_index("ix_executions_started_at", ["started_at"], unique=False)

    if "workflows" in legacy:                       # пересчитываем признаки AI / Telegram-триггер по графу
        bind = op.get_bind()
        for wf_id, nodes in bind.execute(sa.text("SELECT id, nodes FROM workflows")).fetchall():
            if isinstance(nodes, str):
                nodes = json.loads(nodes or "[]")
            types = {n.get("type") for n in (nodes or [])}
            bind.execute(
                sa.text("UPDATE workflows SET is_ai = :ai, has_telegram_trigger = :tg WHERE id = :id"),
                {"ai": bool(types & {"llm", "agent"}), "tg": "telegram_trigger" in types, "id": wf_id},
            )


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    legacy = {t for t in LEGACY_TABLES if insp.has_table(t)}
    if legacy:
        _upgrade_legacy(insp, legacy)

    op.create_table('app_settings',
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('value', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=True),
    sa.Column('admin_email', sa.String(length=320), nullable=True),
    sa.Column('action', sa.String(length=60), nullable=False),
    sa.Column('target', sa.String(length=120), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_log_created_at'), ['created_at'], unique=False)

    if 'executions' not in legacy:
        op.create_table('executions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.Column('is_ai', sa.Boolean(), nullable=False),
        sa.Column('trigger_data', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('logs', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('executions', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_executions_id'), ['id'], unique=False)
            batch_op.create_index(batch_op.f('ix_executions_started_at'), ['started_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_executions_user_id'), ['user_id'], unique=False)

    op.create_table('global_counters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('period', sa.String(length=10), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key', 'period', name='uq_global_counter')
    )
    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('provider_payment_id', sa.String(length=120), nullable=True),
    sa.Column('plan_code', sa.String(length=30), nullable=False),
    sa.Column('period', sa.String(length=10), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('plan_price', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('failure_reason', sa.String(length=255), nullable=True),
    sa.Column('idempotency_key', sa.String(length=64), nullable=False),
    sa.Column('confirmation_url', sa.String(length=512), nullable=True),
    sa.Column('meta', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payments_provider_payment_id'), ['provider_payment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_user_id'), ['user_id'], unique=False)

    op.create_table('plans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('price_month', sa.Integer(), nullable=False),
    sa.Column('price_year', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('max_ai_workflows', sa.Integer(), nullable=True),
    sa.Column('max_regular_workflows', sa.Integer(), nullable=True),
    sa.Column('ai_runs_month', sa.Integer(), nullable=True),
    sa.Column('regular_runs_month', sa.Integer(), nullable=True),
    sa.Column('telegram_triggers', sa.Integer(), nullable=True),
    sa.Column('history_days', sa.Integer(), nullable=True),
    sa.Column('ai_chat_messages_month', sa.Integer(), nullable=True),
    sa.Column('features', sa.JSON(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=True),
    sa.Column('is_public', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_plans_code'), ['code'], unique=True)

    op.create_table('telegram_updates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bot_id', sa.String(length=40), nullable=False),
    sa.Column('update_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bot_id', 'update_id', name='uq_tg_update')
    )
    op.create_table('usage_counters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('period', sa.String(length=10), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'period', 'kind', name='uq_usage')
    )
    with op.batch_alter_table('usage_counters', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usage_counters_user_id'), ['user_id'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=True),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('email_verified', sa.Boolean(), nullable=False),
    sa.Column('is_local', sa.Boolean(), nullable=False),
    sa.Column('settings', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_id'), ['id'], unique=False)

    if 'connections' not in legacy:
        op.create_table('connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('connections', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_connections_id'), ['id'], unique=False)
            batch_op.create_index(batch_op.f('ix_connections_user_id'), ['user_id'], unique=False)

    op.create_table('email_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('email_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_tokens_user_id'), ['user_id'], unique=False)

    op.create_table('refresh_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refresh_tokens_user_id'), ['user_id'], unique=False)

    op.create_table('subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('plan_code', sa.String(length=30), nullable=False),
    sa.Column('period', sa.String(length=10), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('amount_paid', sa.Integer(), nullable=True),
    sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False),
    sa.Column('pending_plan_code', sa.String(length=30), nullable=True),
    sa.Column('pending_period', sa.String(length=10), nullable=True),
    sa.Column('provider', sa.String(length=20), nullable=True),
    sa.Column('payment_method_id', sa.String(length=120), nullable=True),
    sa.Column('payment_method_label', sa.String(length=80), nullable=True),
    sa.Column('renewal_attempts', sa.Integer(), nullable=True),
    sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subscriptions_user_id'), ['user_id'], unique=True)

    if 'workflows' not in legacy:
        op.create_table('workflows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('nodes', sa.JSON(), nullable=True),
        sa.Column('edges', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_ai', sa.Boolean(), nullable=False),
        sa.Column('has_telegram_trigger', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('workflows', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_workflows_id'), ['id'], unique=False)
            batch_op.create_index(batch_op.f('ix_workflows_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('workflows', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workflows_user_id'))
        batch_op.drop_index(batch_op.f('ix_workflows_id'))

    op.drop_table('workflows')
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subscriptions_user_id'))

    op.drop_table('subscriptions')
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_user_id'))

    op.drop_table('refresh_tokens')
    with op.batch_alter_table('email_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_tokens_user_id'))

    op.drop_table('email_tokens')
    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_connections_user_id'))
        batch_op.drop_index(batch_op.f('ix_connections_id'))

    op.drop_table('connections')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_id'))
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
    with op.batch_alter_table('usage_counters', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_usage_counters_user_id'))

    op.drop_table('usage_counters')
    op.drop_table('telegram_updates')
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_plans_code'))

    op.drop_table('plans')
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payments_user_id'))
        batch_op.drop_index(batch_op.f('ix_payments_provider_payment_id'))

    op.drop_table('payments')
    op.drop_table('global_counters')
    with op.batch_alter_table('executions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_executions_user_id'))
        batch_op.drop_index(batch_op.f('ix_executions_started_at'))
        batch_op.drop_index(batch_op.f('ix_executions_id'))

    op.drop_table('executions')
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_log_created_at'))

    op.drop_table('audit_log')
    op.drop_table('app_settings')
