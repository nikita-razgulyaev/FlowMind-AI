from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.types import TypeDecorator

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Всегда хранит и возвращает aware-datetime в UTC (SQLite сам теряет часовой пояс)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


# ───────────────────────── пользователи ─────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(320), nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=True)          # у локального пользователя пароля нет
    name = Column(String(120), default="")
    role = Column(String(20), default="user", nullable=False)    # user | admin
    is_active = Column(Boolean, default=True, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    is_local = Column(Boolean, default=False, nullable=False)
    settings = Column(JSON, default=dict)
    created_at = Column(UTCDateTime, default=utcnow)
    last_login_at = Column(UTCDateTime, nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(UTCDateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    user_agent = Column(String(255), default="")
    created_at = Column(UTCDateTime, default=utcnow)


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)               # verify | reset
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(UTCDateTime, nullable=False)
    used_at = Column(UTCDateTime, nullable=True)
    created_at = Column(UTCDateTime, default=utcnow)


# ───────────────────────── тарифы и оплата ─────────────────────────

class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True)
    code = Column(String(30), nullable=False, unique=True, index=True)   # free | pro | business | local
    name = Column(String(60), nullable=False)
    description = Column(String(255), default="")
    price_month = Column(Integer, default=0, nullable=False)             # в копейках
    price_year = Column(Integer, default=0, nullable=False)              # в копейках, за весь год
    currency = Column(String(3), default="RUB", nullable=False)
    # None = без ограничений
    max_ai_workflows = Column(Integer, nullable=True)
    max_regular_workflows = Column(Integer, nullable=True)
    ai_runs_month = Column(Integer, nullable=True)
    regular_runs_month = Column(Integer, nullable=True)
    telegram_triggers = Column(Integer, nullable=True)
    history_days = Column(Integer, nullable=True)
    ai_chat_messages_month = Column(Integer, nullable=True)
    features = Column(JSON, default=list)                                 # строки для карточки тарифа
    sort_order = Column(Integer, default=0)
    is_public = Column(Boolean, default=True, nullable=False)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    plan_code = Column(String(30), default="free", nullable=False)
    period = Column(String(10), nullable=True)                            # month | year | None (free)
    status = Column(String(20), default="active", nullable=False)         # active | past_due
    current_period_start = Column(UTCDateTime, nullable=True)
    current_period_end = Column(UTCDateTime, nullable=True)
    amount_paid = Column(Integer, default=0)                              # стоимость оплаченного периода (копейки)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    pending_plan_code = Column(String(30), nullable=True)
    pending_period = Column(String(10), nullable=True)
    provider = Column(String(20), nullable=True)
    payment_method_id = Column(String(120), nullable=True)
    payment_method_label = Column(String(80), nullable=True)
    renewal_attempts = Column(Integer, default=0)
    next_retry_at = Column(UTCDateTime, nullable=True)
    created_at = Column(UTCDateTime, default=utcnow)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True, index=True)
    provider = Column(String(20), nullable=False)
    provider_payment_id = Column(String(120), nullable=True, index=True)
    plan_code = Column(String(30), nullable=False)
    period = Column(String(10), nullable=False)
    kind = Column(String(20), default="initial")                          # initial | upgrade | renewal
    amount = Column(Integer, nullable=False)                              # копейки — сколько реально списано
    plan_price = Column(Integer, nullable=False)                          # копейки — полная цена периода
    currency = Column(String(3), default="RUB")
    status = Column(String(20), default="pending", nullable=False)        # pending | requires_action | succeeded | failed | canceled
    failure_reason = Column(String(255), nullable=True)
    idempotency_key = Column(String(64), nullable=False)
    confirmation_url = Column(String(512), nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(UTCDateTime, default=utcnow)
    paid_at = Column(UTCDateTime, nullable=True)


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("user_id", "period", "kind", name="uq_usage"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    period = Column(String(10), nullable=False)                           # YYYY-MM
    kind = Column(String(20), nullable=False)                             # ai_run | regular_run | ai_chat
    count = Column(Integer, default=0, nullable=False)


class GlobalCounter(Base):
    __tablename__ = "global_counters"
    __table_args__ = (UniqueConstraint("key", "period", name="uq_global_counter"),)

    id = Column(Integer, primary_key=True)
    key = Column(String(40), nullable=False)
    period = Column(String(10), nullable=False)                           # YYYY-MM-DD
    count = Column(Integer, default=0, nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(60), primary_key=True)
    value = Column(JSON, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, nullable=True)
    admin_email = Column(String(320), default="")
    action = Column(String(60), nullable=False)
    target = Column(String(120), default="")
    details = Column(JSON, default=dict)
    created_at = Column(UTCDateTime, default=utcnow, index=True)


# ───────────────────────── воркфлоу ─────────────────────────

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    nodes = Column(JSON, default=list)
    edges = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    is_ai = Column(Boolean, default=False, nullable=False)               # есть ли в графе llm/agent-ноды
    has_telegram_trigger = Column(Boolean, default=False, nullable=False)
    created_at = Column(UTCDateTime, default=utcnow)


class Execution(Base):
    __tablename__ = "executions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    workflow_id = Column(Integer, nullable=False)
    status = Column(String, default="pending")
    source = Column(String(20), default="manual")                         # manual | telegram
    is_ai = Column(Boolean, default=False, nullable=False)
    trigger_data = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    logs = Column(JSON, default=list)
    started_at = Column(UTCDateTime, default=utcnow, index=True)
    finished_at = Column(UTCDateTime, nullable=True)


class Connection(Base):
    __tablename__ = "connections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    category = Column(String, nullable=False)   # "ai_api" | "tool"
    provider = Column(String, nullable=False)   # huggingface | openai_compatible | telegram_bot | google_sheets | google_calendar
    name = Column(String, nullable=False)
    config = Column(JSON, default=dict)          # секреты хранятся зашифрованными (см. security.py)
    created_at = Column(UTCDateTime, default=utcnow)


class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"
    __table_args__ = (UniqueConstraint("bot_id", "update_id", name="uq_tg_update"),)

    id = Column(Integer, primary_key=True)
    bot_id = Column(String(40), nullable=False)
    update_id = Column(Integer, nullable=False)
    created_at = Column(UTCDateTime, default=utcnow)
