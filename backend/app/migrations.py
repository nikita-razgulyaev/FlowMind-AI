import asyncio
import logging
from pathlib import Path

log = logging.getLogger("flowmind.migrations")
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _upgrade() -> None:
    try:
        from alembic import command
        from alembic.config import Config
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Пакет alembic не установлен. Выполните: pip install -r requirements.txt"
        ) from exc

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "db_migrations"))
    command.upgrade(cfg, "head")


async def run_migrations() -> None:
    log.info("Применяю миграции БД…")
    await asyncio.to_thread(_upgrade)
