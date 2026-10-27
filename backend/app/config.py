"""Единая конфигурация сервиса. Все параметры берутся из переменных окружения / .env."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


def normalize_database_url(raw: str) -> tuple[URL, dict]:
    """Приводит URL из .env / Render / Heroku к виду, понятному async-драйверам."""
    connect_args: dict = {}
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://"):]
    if raw.startswith("sqlite:///"):
        raw = "sqlite+aiosqlite:///" + raw[len("sqlite:///"):]
    url = make_url(raw)
    if url.drivername == "postgresql+asyncpg":
        query = dict(url.query)
        sslmode = query.pop("sslmode", None)
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = sslmode
        url = url.set(query=query)
    return url, connect_args


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    # --- режим развёртывания ---
    deployment_mode: str = "local"            # local | cloud
    auth_enabled: Optional[bool] = None       # по умолчанию: включено в cloud, выключено в local
    database_url: str = "sqlite+aiosqlite:///./flowmind.db"
    static_dir: str = ""                      # папка со сборкой фронтенда (раздаётся самим backend)
    auto_migrate: bool = True                 # применять миграции Alembic при старте

    # --- безопасность ---
    secret_key: str = "dev-insecure-change-me"
    encryption_key: str = ""                  # ключ шифрования секретов подключений (по умолчанию = secret_key)
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    cookie_secure: Optional[bool] = None
    cors_origins: str = "http://localhost:5173"
    public_base_url: str = ""                 # https://flowmind.example.com (нужен для вебхуков и возврата с оплаты)
    frontend_url: str = "http://localhost:5173"

    # --- аккаунты ---
    admin_email: str = ""
    admin_password: str = ""
    require_email_verification: bool = False
    demo_mode: bool = False                   # показывать ссылки из писем прямо в ответе API (только для демо!)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "FlowMind AI <no-reply@flowmind.local>"
    smtp_starttls: bool = True

    # --- оплата ---
    payment_provider: str = "mock"            # mock | yookassa
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_receipts: bool = False           # отправлять чек по 54-ФЗ вместе с платежом
    yookassa_vat_code: int = 1
    yookassa_tax_system_code: Optional[int] = None

    # --- LLM ---
    llm_mode: str = ""                        # local | cloud; по умолчанию зависит от deployment_mode
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"
    platform_llm_base_url: str = "https://router.huggingface.co/v1"
    platform_llm_api_key: str = Field(
        default="", validation_alias=AliasChoices("PLATFORM_LLM_API_KEY", "HF_TOKEN")
    )
    platform_llm_model: str = Field(
        default="openai/gpt-oss-120b:groq",
        validation_alias=AliasChoices("PLATFORM_LLM_MODEL", "HF_MODEL"),
    )
    ai_daily_cap: int = 5000                  # общий суточный потолок запросов к ключу платформы

    # --- Telegram ---
    telegram_mode: str = "auto"               # auto | webhook | polling | off

    # --- Google OAuth ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    google_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"

    # --- лимиты безопасности исполнения ---
    max_execution_seconds: int = 120
    max_nodes_per_workflow: int = 60
    max_parallel_executions_per_user: int = 3

    # ---------------- вычисляемые свойства ----------------
    @property
    def is_cloud(self) -> bool:
        return self.deployment_mode.strip().lower() == "cloud"

    @property
    def is_local(self) -> bool:
        return not self.is_cloud

    @property
    def auth_required(self) -> bool:
        return self.is_cloud if self.auth_enabled is None else self.auth_enabled

    @property
    def default_llm_mode(self) -> str:
        return self.llm_mode or ("cloud" if self.is_cloud else "local")

    @property
    def base_url(self) -> str:
        return (
            self.public_base_url or os.getenv("RENDER_EXTERNAL_URL", "") or ""
        ).rstrip("/")

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_cloud and self.base_url.startswith("https://")

    @property
    def effective_telegram_mode(self) -> str:
        mode = self.telegram_mode.lower()
        if mode != "auto":
            return mode
        if self.is_local:
            return "polling"
        return "webhook" if self.base_url else "off"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def google_redirect(self) -> str:
        if self.google_redirect_uri:
            return self.google_redirect_uri
        return f"{self.base_url or 'http://localhost:8000'}/api/oauth/google/callback"

    @property
    def app_url(self) -> str:
        """Адрес, на который пользователь возвращается из внешних сервисов (оплата, письма)."""
        return self.base_url or self.frontend_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
