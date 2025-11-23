from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import desc, select

from apps.bot.core.wallets import add_coins_cash, get_wallet_balance
from apps.bot.db.models import CrashBet, CrashBetStatus, CrashRound, CrashRoundStatus, User
from apps.bot.services import crash as crash_service


@pytest.mark.asyncio
async def test_crash_place_bet_deducts_balance(session):
    user = User(tg_id=555, username="crash_tester")
    session.add(user)
    await session.flush()

    await add_coins_cash(session, user.id, 1_000)

    snapshot = await crash_service.place_bet(session, user=user, amount=200)

    assert snapshot.bet is not None
    assert snapshot.bet["amount"] == 200
    wallet = await get_wallet_balance(session, user.id)
    assert wallet.coins_cash == 800

    bet = await session.scalar(select(CrashBet).order_by(desc(CrashBet.id)))
    assert bet is not None
    assert bet.amount_cash == 200
    assert bet.status == CrashBetStatus.ACTIVE.value
    await session.refresh(user)
    assert user.paid_crash_bets_count == 1


@pytest.mark.asyncio
async def test_crash_cashout_returns_payout(session):
    user = User(tg_id=777, username="cashout")
    session.add(user)
    await session.flush()

    await add_coins_cash(session, user.id, 1_000)
    await crash_service.place_bet(session, user=user, amount=100)

    round_obj = await session.scalar(select(CrashRound).order_by(desc(CrashRound.id)))
    assert round_obj is not None

    now = crash_service._now()
    round_obj.bet_ends_at = now - timedelta(seconds=2)
    round_obj.crash_at = now + timedelta(seconds=10)
    round_obj.status = CrashRoundStatus.BETTING.value
    round_obj.crash_point = Decimal("3.0")
    await session.flush()

    snapshot = await crash_service.cashout(session, user=user)

    assert snapshot.cashout is not None
    assert snapshot.cashout["payout"] >= 100
    bet = await session.scalar(select(CrashBet).order_by(desc(CrashBet.id)))
    assert bet.status == CrashBetStatus.CASHED_OUT.value

    wallet = await get_wallet_balance(session, user.id)
    assert wallet.coins_cash > 900


@pytest.mark.asyncio
async def test_auto_cashout_triggers(session):
    crash_service.set_auto_cashout_consumer(None)
    crash_service.consume_auto_cashout_events()
    user = User(tg_id=9999, username="auto")
    session.add(user)
    await session.flush()

    await add_coins_cash(session, user.id, 1_000)
    await crash_service.place_bet(session, user=user, amount=100, auto_cashout=1.1)

    round_obj = await session.scalar(select(CrashRound).order_by(desc(CrashRound.id)))
    assert round_obj is not None

    now = crash_service._now()
    round_obj.bet_ends_at = now - timedelta(seconds=2)
    round_obj.crash_at = now + timedelta(seconds=10)
    round_obj.status = CrashRoundStatus.FLYING.value
    round_obj.crash_point = Decimal("3.0")
    await session.flush()

    await crash_service.get_round_summary(session)

    events = crash_service.consume_auto_cashout_events()
    assert len(events) == 1
    event = events[0]
    assert event.user_id == user.id
    assert event.snapshot.cashout is not None
    wallet = await get_wallet_balance(session, user.id)
    assert wallet.coins_cash > 900
    crash_service.set_auto_cashout_consumer(None)


@pytest.mark.asyncio
async def test_auto_cashout_events_buffer_when_no_consumer(session):
    crash_service.set_auto_cashout_consumer(None)
    crash_service.consume_auto_cashout_events()
    user = User(tg_id=12345, username="no_events")
    session.add(user)
    await session.flush()

    await add_coins_cash(session, user.id, 500)
    await crash_service.place_bet(session, user=user, amount=100, auto_cashout=1.05)

    round_obj = await session.scalar(select(CrashRound).order_by(desc(CrashRound.id)))
    assert round_obj is not None

    now = crash_service._now()
    round_obj.bet_ends_at = now - timedelta(seconds=2)
    round_obj.crash_at = now + timedelta(seconds=5)
    round_obj.status = CrashRoundStatus.FLYING.value
    round_obj.crash_point = Decimal("2.0")
    await session.flush()

    await crash_service.get_round_summary(session)

    events = crash_service.consume_auto_cashout_events()
    assert len(events) == 1
