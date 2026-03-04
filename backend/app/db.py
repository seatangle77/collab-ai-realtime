from __future__ import annotations

from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .settings import settings


class DBNotConfiguredError(RuntimeError):
    pass


@lru_cache
def get_engine() -> AsyncEngine:
    try:
        url = settings.sqlalchemy_database_url()
    except RuntimeError as e:
        raise DBNotConfiguredError(str(e)) from e

    return create_async_engine(
        url,
        pool_pre_ping=True,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def get_db():
    async with get_sessionmaker()() as session:
        yield session


async def ping_db() -> None:
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))
