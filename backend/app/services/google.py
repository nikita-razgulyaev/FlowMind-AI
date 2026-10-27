"""Обновление Google OAuth-токенов подключения."""
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Connection
from ..security import decrypt_config, encrypt_value

GOOGLE_PROVIDERS = {"google_sheets", "google_calendar"}


async def refresh_if_needed(conn: Connection, db: AsyncSession) -> dict:
    """Возвращает расшифрованный config; при истёкшем access_token обновляет его через refresh_token."""
    cfg = decrypt_config(conn.config)
    obtained_at = cfg.get("obtained_at")
    expires_in = cfg.get("expires_in", 3600)
    refresh_token = cfg.get("refresh_token")

    expired = True
    if obtained_at:
        try:
            obtained = datetime.fromisoformat(obtained_at)
            if obtained.tzinfo is None:
                obtained = obtained.replace(tzinfo=timezone.utc)
            expired = datetime.now(timezone.utc) >= obtained + timedelta(seconds=expires_in - 60)
        except ValueError:
            expired = True
    if not expired or not refresh_token:
        return cfg

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(settings.google_token_url, data={
            "refresh_token": refresh_token,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "grant_type": "refresh_token",
        })
    if r.status_code != 200:
        return cfg
    tokens = r.json()
    cfg["access_token"] = tokens["access_token"]
    cfg["expires_in"] = tokens.get("expires_in", expires_in)
    cfg["obtained_at"] = datetime.now(timezone.utc).isoformat()

    stored = dict(conn.config or {})
    stored["access_token"] = encrypt_value(cfg["access_token"])
    stored["expires_in"] = cfg["expires_in"]
    stored["obtained_at"] = cfg["obtained_at"]
    conn.config = stored
    db.add(conn)
    await db.commit()
    return cfg
