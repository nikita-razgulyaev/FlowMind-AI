"""Пароли, JWT, одноразовые токены и шифрование секретов подключений."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from .config import settings

_hasher = PasswordHasher()
ENC_PREFIX = "enc:"


# ───── пароли ─────
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ───── JWT access-токены ─────
def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> Optional[int]:
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if data.get("typ") != "access":
        return None
    try:
        return int(data["sub"])
    except (KeyError, ValueError):
        return None


# ───── одноразовые токены (refresh, письма) ─────
def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sign(value: str, purpose: str, length: int = 32) -> str:
    """Детерминированная подпись для секретов вебхуков и OAuth state."""
    mac = hmac.new(settings.secret_key.encode(), f"{purpose}:{value}".encode(), hashlib.sha256)
    return mac.hexdigest()[:length]


def constant_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ───── шифрование секретов ─────
def _fernet() -> Fernet:
    seed = (settings.encryption_key or settings.secret_key).encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
    return Fernet(key)


def encrypt_value(value: str) -> str:
    if not isinstance(value, str) or value.startswith(ENC_PREFIX):
        return value
    return ENC_PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt_value(value: Any) -> Any:
    if not isinstance(value, str) or not value.startswith(ENC_PREFIX):
        return value          # старые (незашифрованные) значения читаются как есть
    try:
        return _fernet().decrypt(value[len(ENC_PREFIX):].encode()).decode()
    except InvalidToken:
        return ""


SECRET_KEYS = {"api_key", "bot_token", "token", "password", "secret", "access_token", "refresh_token"}


def encrypt_config(config: dict) -> dict:
    return {
        k: (encrypt_value(v) if k in SECRET_KEYS and isinstance(v, str) and v else v)
        for k, v in (config or {}).items()
    }


def decrypt_config(config: dict) -> dict:
    return {k: (decrypt_value(v) if k in SECRET_KEYS else v) for k, v in (config or {}).items()}


def mask_config(config: dict) -> dict:
    masked = {}
    for k, v in (config or {}).items():
        if k in SECRET_KEYS and isinstance(v, str) and v:
            plain = decrypt_value(v)
            masked[k] = ("••••••" + plain[-4:]) if len(plain) > 4 else "••••••"
        else:
            masked[k] = v
    return masked
