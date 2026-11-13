"""Единая конфигурация сервиса. Все параметры берутся из переменных окружения / .env."""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Optional

from pydantic import AliasChoices, Field, field_validator
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


# Основная модель по умолчанию: OrcaRouter, бесплатная DeepSeek V4 Flash (контекст 1M, вызов инструментов, JSON). Ключ берётся из ORCAROUTER_API_KEY.
DEFAULT_PLATFORM_LLM_PROVIDERS = [
    {"name": "orcarouter", "base_url": "https://api.orcarouter.ai/v1", "model": "deepseek/deepseek-v4-flash-free", "api_key_env": "ORCAROUTER_API_KEY"},
]


@lru_cache
def _dotenv() -> dict:
    try:
        from dotenv import dotenv_values
        return {k: v for k, v in dotenv_values(".env").items() if v}
    except Exception:
        return {}


def _env_value(name: str) -> str:
    """Секрет по имени переменной: из окружения сервера или из файла .env."""
    return (os.environ.get(name) or _dotenv().get(name) or "") if name else ""


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

    @field_validator("secret_key", mode="before")
    @classmethod
    def _secret_key_not_empty(cls, v):
        """Пустой SECRET_KEY= в .env не должен затирать дефолт — иначе JWT падает с InvalidKeyError."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return "dev-insecure-change-me"
        return v

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
    # Все модели встроенного AI одним списком, первая — основная, остальные запасные (переключение при сбое).
    # JSON: [{"name": "...", "base_url": "https://.../v1", "model": "...", "api_key_env": "ИМЯ_ПЕРЕМЕННОЙ"}], вместо api_key_env можно указать api_key.
    # Если список не задан, используется модель по умолчанию (DEFAULT_PLATFORM_LLM_PROVIDERS) с ключом из ORCAROUTER_API_KEY.
    platform_llm_providers_raw: str = Field(default="", validation_alias=AliasChoices("PLATFORM_LLM_PROVIDERS"))
    ai_daily_cap: int = 5000                  # общий суточный потолок запросов к ключу платформы
    platform_llm_cooldown_seconds: int = 60   # на сколько отложить провайдера после сбоя (при повторных сбоях растёт, максимум 10 минут)

    # --- Telegram ---
    telegram_mode: str = "auto"               # auto | webhook | polling | off

    # --- Google OAuth ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    google_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"

    # --- Яндекс / Mail.ru OAuth ---
    yandex_client_id: str = ""
    yandex_client_secret: str = ""
    yandex_redirect_uri: str = ""
    mailru_client_id: str = ""
    mailru_client_secret: str = ""
    mailru_redirect_uri: str = ""
    mailru_mail_scopes: str = "userinfo mail.imap"   # права для почты Mail.ru; уточняйте в кабинете o2.mail.ru

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
    def platform_llm_providers(self) -> list[dict]:
        """Цепочка моделей встроенного AI по порядку: первая основная, дальше запасные. Записи без ключа или с адресом не по https пропускаются."""
        raw = (self.platform_llm_providers_raw or "").strip()
        items = DEFAULT_PLATFORM_LLM_PROVIDERS
        if raw:
            try:
                items = json.loads(raw)
            except ValueError:
                logging.getLogger(__name__).warning("PLATFORM_LLM_PROVIDERS: некорректный JSON, используется список по умолчанию")
        chain = []
        for i, item in enumerate(items if isinstance(items, list) else []):
            if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item.get(k) for k in ("base_url", "model")):
                continue
            key = item.get("api_key") or _env_value(item.get("api_key_env", ""))
            if not key or not item["base_url"].startswith("https://"):
                continue
            chain.append({"name": str(item.get("name") or f"model{i + 1}")[:40], "base_url": item["base_url"], "api_key": key,
                          "model": item["model"], "max_tokens": int(item.get("max_tokens") or 1500)})
        return chain

    @property
    def platform_llm_configured(self) -> bool:
        return bool(self.platform_llm_providers)

    def oauth_redirect(self, family: str) -> str:
        """Адрес возврата для OAuth-входа; его нужно указать в кабинете разработчика соответствующего сервиса."""
        if family == "google":
            return self.google_redirect
        override = getattr(self, f"{family}_redirect_uri", "")
        return override or f"{self.base_url or 'http://localhost:8000'}/api/oauth/{family}/callback"

    @property
    def app_url(self) -> str:
        """Адрес, на который пользователь возвращается из внешних сервисов (оплата, письма)."""
        return self.base_url or self.frontend_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
