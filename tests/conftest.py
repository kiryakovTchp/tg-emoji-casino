from __future__ import annotations

import pytest_asyncio
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.bot.db import Base
from apps.bot.db.models import TurnoverRule


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            insert(TurnoverRule),
            [
                {"game": "slot", "contribution": 100},
                {"game": "crash", "contribution": 50},
                {"game": "duel", "contribution": 25},
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as db:
        yield db
    await engine.dispose()
