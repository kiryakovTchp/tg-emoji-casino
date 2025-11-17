from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.bot.core.awards import apply_turnover, create_bonus_award, try_unlock_bonuses
from apps.bot.core.wallets import add_coins_cash, get_wallet_balance
from apps.bot.db import Base
from apps.bot.db.models import TurnoverRule, User


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(TurnoverRule.__table__.insert(), [
            {"game": "slot", "contribution": 100},
            {"game": "crash", "contribution": 50},
            {"game": "duel", "contribution": 25},
        ])

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        user = User(tg_id=999, username="demo")
        session.add(user)
        await session.flush()

        await add_coins_cash(session, user.id, 500, reason="seed")
        await create_bonus_award(session, user.id, kind="welcome", granted=1000, wr_mult=1.0, cap_cashout=2000)
        await apply_turnover(session, user.id, "slot", 1000)
        result = await try_unlock_bonuses(session, user.id)
        wallet = await get_wallet_balance(session, user.id)
        await session.commit()

        print("Unlocked awards:", result)
        print("Wallet -> cash:", wallet.coins_cash, "bonus:", wallet.coins_bonus)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
