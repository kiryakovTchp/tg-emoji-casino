from __future__ import annotations

import pytest
from sqlalchemy import select

from apps.bot.core.awards import apply_turnover, create_bonus_award, try_unlock_bonuses
from apps.bot.core.wallets import add_coins_bonus, add_coins_cash, consume_coins, get_wallet_balance
from apps.bot.db.models import BonusAwardStatus, Ledger, User


@pytest.mark.asyncio
async def test_wallet_add_and_consume(session):
    user = User(tg_id=1001, username="tester")
    session.add(user)
    await session.flush()

    await add_coins_cash(session, user.id, 1_000)
    await add_coins_bonus(session, user.id, 500)

    wallet = await get_wallet_balance(session, user.id)
    assert wallet.coins_cash == 1_000
    assert wallet.coins_bonus == 500

    spent = await consume_coins(session, user.id, 700, prefer="cash_first")
    assert spent.cash == 700
    assert spent.bonus == 0

    wallet = await get_wallet_balance(session, user.id)
    assert wallet.coins_cash == 300
    assert wallet.coins_bonus == 500

    spent_bonus = await consume_coins(session, user.id, 200, prefer="bonus_first")
    assert spent_bonus.cash == 0
    assert spent_bonus.bonus == 200

    wallet = await get_wallet_balance(session, user.id)
    assert wallet.coins_cash == 300
    assert wallet.coins_bonus == 300

    entries = (await session.scalars(select(Ledger).where(Ledger.user_id == user.id))).all()
    assert len(entries) >= 4  # two credits + two debits


@pytest.mark.asyncio
async def test_bonus_award_unlock_flow(session):
    user = User(tg_id=2002, username="bonus")
    session.add(user)
    await session.flush()

    award = await create_bonus_award(
        session,
        user.id,
        kind="welcome",
        granted=1_000,
        wr_mult=1.0,
        cap_cashout=2_000,
    )

    await apply_turnover(session, user.id, "slot", stake=1_000)

    result = await try_unlock_bonuses(session, user.id)
    wallet = await get_wallet_balance(session, user.id)
    await session.refresh(award)

    assert wallet.coins_cash == 1_000
    assert wallet.coins_bonus == 0
    assert result["awards"][0]["transferred"] == 1_000
    assert award.status == BonusAwardStatus.COMPLETED.value
