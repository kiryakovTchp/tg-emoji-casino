from __future__ import annotations

import hashlib
import math
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.core.awards import apply_turnover
from apps.bot.core.wallets import add_coins_cash, consume_coins, get_wallet_balance
from apps.bot.db.models import (
    CrashBet,
    CrashBetStatus,
    CrashRound,
    CrashRoundStatus,
    User,
)
from apps.bot.infra.settings import get_settings

settings = get_settings()


@dataclass
class CrashSnapshot:
    session: dict
    user: dict
    balance: dict
    bet: dict | None = None
    cashout: dict | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        # Remove None entries for optional blocks
        if data["bet"] is None:
            data.pop("bet")
        if data["cashout"] is None:
            data.pop("cashout")
        return data


@dataclass
class AutoCashoutEvent:
    user_id: int
    snapshot: CrashSnapshot


AutoCashoutCallback = Callable[[AutoCashoutEvent], Awaitable[None]]


_auto_cashout_events: list[AutoCashoutEvent] = []
_auto_cashout_consumer: AutoCashoutCallback | None = None


def set_auto_cashout_consumer(callback: AutoCashoutCallback | None) -> None:
    global _auto_cashout_consumer
    _auto_cashout_consumer = callback


def consume_auto_cashout_events() -> list[AutoCashoutEvent]:
    events = list(_auto_cashout_events)
    _auto_cashout_events.clear()
    return events


async def _emit_auto_cashout(event: AutoCashoutEvent) -> None:
    if _auto_cashout_consumer:
        await _auto_cashout_consumer(event)
    else:
        _auto_cashout_events.append(event)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _crash_point_from_seed(seed: str) -> float:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    value = int(digest[:13], 16)
    if value == 0:
        return 1.0
    base = (2**52 - value % (2**52)) / 2**52
    crash_point = max(1.01, round(base * 20, 2))
    return crash_point


async def _create_round(session: AsyncSession) -> CrashRound:
    now = _now()
    seed = secrets.token_hex(32)
    seed_hash = hashlib.sha256(seed.encode()).hexdigest()
    bet_end = now + timedelta(milliseconds=settings.crash_bet_duration_ms)
    crash_point = _crash_point_from_seed(seed)
    
    # Exponential growth: M(t) = e^(k * t)
    # k = 0.00006 (approx 6% per second, standard-ish)
    # t = ln(M) / k
    k = 0.00006
    duration_ms = int(math.log(crash_point) / k)
    # Add a small buffer or minimum duration
    duration_ms = max(1000, duration_ms)
    
    crash_at = bet_end + timedelta(milliseconds=duration_ms)
    round_obj = CrashRound(
        status=CrashRoundStatus.BETTING.value,
        seed=seed,
        seed_hash=seed_hash,
        crash_point=crash_point,
        bet_ends_at=bet_end,
        crash_at=crash_at,
    )
    session.add(round_obj)
    await session.flush()
    return round_obj


async def _active_round(session: AsyncSession) -> CrashRound:
    round_obj = await session.scalar(select(CrashRound).order_by(desc(CrashRound.id)).limit(1))
    if round_obj is None:
        return await _create_round(session)
    await _sync_round(session, round_obj)
    await _auto_cashout_bets(session, round_obj)
    if round_obj.status == CrashRoundStatus.CRASHED.value and round_obj.settled_at:
        return await _create_round(session)
    return round_obj


async def _sync_round(session: AsyncSession, round_obj: CrashRound) -> None:
    now = _now()
    updated = False
    if round_obj.status == CrashRoundStatus.BETTING.value and now >= round_obj.bet_ends_at:
        round_obj.status = CrashRoundStatus.FLYING.value
        updated = True
    if round_obj.status == CrashRoundStatus.FLYING.value and now >= round_obj.crash_at:
        round_obj.status = CrashRoundStatus.CRASHED.value
        updated = True
    if updated:
        await session.flush()
    if round_obj.status == CrashRoundStatus.CRASHED.value:
        await _settle_round(session, round_obj)


async def _settle_round(session: AsyncSession, round_obj: CrashRound) -> None:
    if round_obj.settled_at:
        return
    now = _now()
    bets = (
        await session.scalars(
            select(CrashBet).where(
                CrashBet.round_id == round_obj.id,
                CrashBet.status == CrashBetStatus.ACTIVE.value,
            )
        )
    ).all()
    for bet in bets:
        bet.status = CrashBetStatus.CRASHED.value
        bet.updated_at = now
        await apply_turnover(session, bet.user_id, "crash", bet.amount_cash + bet.amount_bonus)
    round_obj.settled_at = now
    await session.flush()


async def _get_active_bet(session: AsyncSession, round_id: int, user_id: int) -> CrashBet | None:
    return await session.scalar(
        select(CrashBet)
            .where(
                CrashBet.round_id == round_id,
                CrashBet.user_id == user_id,
                CrashBet.status == CrashBetStatus.ACTIVE.value,
            )
            .order_by(desc(CrashBet.id))
    )


def _session_payload(round_obj: CrashRound) -> dict:
    crash_point = float(round_obj.crash_point) if round_obj.status == CrashRoundStatus.CRASHED.value else None
    return {
        "id": round_obj.id,
        "phase": round_obj.status,
        "seed": round_obj.seed_hash if round_obj.status != CrashRoundStatus.CRASHED.value else round_obj.seed,
        "startTime": int(round_obj.created_at.timestamp() * 1000),
        "betEndTime": int(round_obj.bet_ends_at.timestamp() * 1000),
        "crashTime": int(round_obj.crash_at.timestamp() * 1000),
        "crashPoint": crash_point,
    }


def _balance_payload(wallet) -> dict:
    total = wallet.coins_cash + wallet.coins_bonus
    return {
        "cash": wallet.coins_cash,
        "bonus": wallet.coins_bonus,
        "total": total,
    }


def _user_payload(wallet, bet: CrashBet | None) -> dict:
    total = wallet.coins_cash + wallet.coins_bonus
    bet_amount = None
    if bet:
        bet_amount = bet.amount_cash + bet.amount_bonus
    return {
        "betAmount": bet_amount,
        "cashoutMultiplier": float(bet.cashout_multiplier) if bet and bet.cashout_multiplier else None,
        "balance": total,
    }


def _current_multiplier(round_obj: CrashRound) -> float:
    if round_obj.status == CrashRoundStatus.BETTING.value:
        return 1.0
    if round_obj.status == CrashRoundStatus.CRASHED.value:
        return float(round_obj.crash_point or 1.0)
    
    elapsed_ms = max(0.0, (_now() - round_obj.bet_ends_at).total_seconds() * 1000)
    k = 0.00006
    current = math.exp(k * elapsed_ms)
    
    # Cap at crash_point if we somehow exceeded it but haven't processed crash yet
    crash_point = float(round_obj.crash_point or 1.0)
    return min(crash_point, round(current, 4))


async def _build_snapshot(session: AsyncSession, round_obj: CrashRound, user_id: int) -> CrashSnapshot:
    wallet = await get_wallet_balance(session, user_id)
    bet = await _get_active_bet(session, round_obj.id, user_id)
    return CrashSnapshot(
        session=_session_payload(round_obj),
        user=_user_payload(wallet, bet),
        balance=_balance_payload(wallet),
        bet=_bet_payload(bet),
    )


def _bet_payload(bet: CrashBet | None) -> dict | None:
    if bet is None:
        return None
    return {
        "id": bet.id,
        "roundId": bet.round_id,
        "amount": bet.amount_cash + bet.amount_bonus,
        "status": bet.status,
        "cashoutMultiplier": float(bet.cashout_multiplier) if bet.cashout_multiplier else None,
    }


async def _finalize_cashout(session: AsyncSession, round_obj: CrashRound, bet: CrashBet, multiplier: float) -> int:
    payout_total = int((bet.amount_cash + bet.amount_bonus) * multiplier)
    if payout_total <= 0:
        raise ValueError("Invalid payout")
    await add_coins_cash(
        session,
        bet.user_id,
        payout_total,
        reason="crash_payout",
        metadata={"round_id": round_obj.id, "multiplier": multiplier},
    )
    bet.status = CrashBetStatus.CASHED_OUT.value
    bet.cashout_multiplier = multiplier
    bet.payout_cash = payout_total
    bet.cashed_at = _now()
    await apply_turnover(session, bet.user_id, "crash", bet.amount_cash + bet.amount_bonus)
    return payout_total


async def _auto_cashout_bets(session: AsyncSession, round_obj: CrashRound) -> None:
    if round_obj.status != CrashRoundStatus.FLYING.value:
        return
    multiplier = _current_multiplier(round_obj)
    bets = (
        await session.scalars(
            select(CrashBet).where(
                CrashBet.round_id == round_obj.id,
                CrashBet.status == CrashBetStatus.ACTIVE.value,
                CrashBet.auto_cashout.is_not(None),
                CrashBet.auto_cashout <= multiplier,
            )
        )
    ).all()
    for bet in bets:
        payout_total = await _finalize_cashout(session, round_obj, bet, multiplier)
        await session.flush()
        snapshot = await _build_snapshot(session, round_obj, bet.user_id)
        snapshot.cashout = {
            "multiplier": multiplier,
            "payout": payout_total,
            "betId": bet.id,
        }
        await _emit_auto_cashout(AutoCashoutEvent(user_id=bet.user_id, snapshot=snapshot))


async def get_state(session: AsyncSession, user_id: int) -> CrashSnapshot:
    round_obj = await _active_round(session)
    return await _build_snapshot(session, round_obj, user_id)


async def get_round_summary(session: AsyncSession) -> dict:
    round_obj = await _active_round(session)
    return _session_payload(round_obj)


async def get_recent_history(session: AsyncSession, limit: int = 20) -> list[dict]:
    rows = (
        await session.scalars(
            select(CrashRound)
            .where(CrashRound.status == CrashRoundStatus.CRASHED.value)
            .order_by(desc(CrashRound.id))
            .limit(limit)
        )
    ).all()
    history = []
    for row in rows:
        history.append(
            {
                "roundId": row.id,
                "crashPoint": float(row.crash_point or 1.0),
                "crashedAt": int(row.crash_at.timestamp() * 1000),
            }
        )
    return history


def _ensure_bet_limits(amount: int) -> None:
    if amount < settings.crash_bet_min or amount > settings.crash_bet_max:
        raise ValueError("Bet outside allowed limits")


async def place_bet(
    session: AsyncSession,
    *,
    user: User,
    amount: int,
    auto_cashout: float | None = None,
) -> CrashSnapshot:
    _ensure_bet_limits(amount)
    round_obj = await _active_round(session)
    if round_obj.status != CrashRoundStatus.BETTING.value or _now() >= round_obj.bet_ends_at:
        raise ValueError("Betting phase is closed")
    existing = await _get_active_bet(session, round_obj.id, user.id)
    if existing:
        raise ValueError("Bet already placed in this round")

    consumption = await consume_coins(
        session,
        user.id,
        amount,
        prefer="auto_bonus_when_active",
        reason="crash_bet",
        metadata={"round_id": round_obj.id},
    )
    bet = CrashBet(
        round_id=round_obj.id,
        user_id=user.id,
        amount_cash=consumption.cash,
        amount_bonus=consumption.bonus,
        auto_cashout=auto_cashout,
    )
    session.add(bet)
    if consumption.cash > 0:
        user.paid_crash_bets_count += 1
    await session.flush()
    await session.commit()
    snapshot = await _build_snapshot(session, round_obj, user.id)
    snapshot.bet = _bet_payload(bet)
    return snapshot


async def cashout(session: AsyncSession, *, user: User) -> CrashSnapshot:
    round_obj = await _active_round(session)
    if round_obj.status != CrashRoundStatus.FLYING.value:
        raise ValueError("Cashout unavailable")
    bet = await _get_active_bet(session, round_obj.id, user.id)
    if bet is None:
        raise ValueError("No active bet")
    multiplier = _current_multiplier(round_obj)
    payout_total = await _finalize_cashout(session, round_obj, bet, multiplier)
    await session.flush()
    await session.commit()
    snapshot = await _build_snapshot(session, round_obj, user.id)
    snapshot.cashout = {
        "multiplier": multiplier,
        "payout": payout_total,
        "betId": bet.id,
    }
    return snapshot
