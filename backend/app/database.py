from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from .config import normalize_database_url, settings

_url, _connect_args = normalize_database_url(settings.database_url)

engine = create_async_engine(_url, echo=False, connect_args=_connect_args, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    async with async_session() as session:
        yield session
