from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .settings import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self._engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False, class_=AsyncSession)

    @property
    def engine(self):
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncSession:
        async with self._session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self._engine.dispose()
