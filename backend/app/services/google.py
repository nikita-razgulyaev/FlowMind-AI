"""Обновление OAuth-токенов подключений (Google, Яндекс, Mail.ru). Имя файла сохранено для совместимости."""
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Connection
from ..security import decrypt_config, encrypt_value
from . import oauth
from .oauth import OAUTH_PROVIDERS

GOOGLE_PROVIDERS = OAUTH_PROVIDERS      # прежнее имя, на него ссылается runner


async def refresh_if_needed(conn: Connection, db: AsyncSession) -> dict:
    """Возвращает расшифрованный config. Истёкший access_token обновляется; при отзыве доступа подключение помечается needs_reauth."""
    cfg = decrypt_config(conn.config)
    if not oauth.is_expired(cfg) or not cfg.get("refresh_token"):
        return cfg
    fresh = await oauth.refresh_tokens(conn.provider, cfg)
    if fresh == "temporary":
        return cfg
    stored = dict(conn.config or {})
    if fresh is None:
        stored["needs_reauth"] = True
        cfg["needs_reauth"] = True
    else:
        cfg.update(fresh)
        for key in ("access_token", "refresh_token"):
            if fresh.get(key):
                stored[key] = encrypt_value(fresh[key])
        for key in ("expires_in", "obtained_at", "scope", "needs_reauth"):
            if key in fresh and fresh[key] is not None:
                stored[key] = fresh[key]
    conn.config = stored
    db.add(conn)
    await db.commit()
    return cfg
