from __future__ import annotations

from datetime import datetime, timedelta

from aiogram.types import Chat
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.db.models import Duel, DuelState

DUEL_PAIR_LIMIT_PER_DAY = 3
ACTIVE_STATES = (DuelState.PENDING.value, DuelState.RUNNING.value)


async def user_has_active_duel(session: AsyncSession, user_id: int) -> bool:
    stmt = select(func.count()).where(
        Duel.state.in_(ACTIVE_STATES),
        or_(Duel.starter_id == user_id, Duel.opponent_id == user_id),
    )
    total = await session.scalar(stmt)
    return bool(total)


async def create_duel(
    session: AsyncSession,
    *,
    chat_id: int,
    starter_id: int,
    stake_amount: int,
    stake_currency: str,
) -> Duel:
    duel = Duel(
        chat_id=chat_id,
        starter_id=starter_id,
        stake_amount=stake_amount,
        stake_currency=stake_currency,
        rounds=[],
    )
    session.add(duel)
    await session.flush()
    return duel


async def get_duel(session: AsyncSession, duel_id: int, *, for_update: bool = False) -> Duel | None:
    if for_update:
        return await session.get(Duel, duel_id, with_for_update=True)
    return await session.get(Duel, duel_id)


async def cancel_duel(session: AsyncSession, duel: Duel, *, state: str = DuelState.CANCELLED.value) -> None:
    duel.state = state
    duel.finished_at = datetime.utcnow()


async def mark_message(session: AsyncSession, duel: Duel, *, message_id: int, thread_id: int | None = None) -> None:
    duel.message_id = message_id
    duel.thread_id = thread_id


async def can_start_pair(session: AsyncSession, user_a: int, user_b: int) -> bool:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    pair_key = build_pair_key(user_a, user_b)
    stmt = select(func.count()).where(
        Duel.pair_key == pair_key,
        Duel.finished_at >= today_start,
        Duel.state == DuelState.FINISHED.value,
    )
    total = await session.scalar(stmt)
    return total < DUEL_PAIR_LIMIT_PER_DAY


def build_pair_key(user_a: int, user_b: int) -> str:
    return f"{min(user_a, user_b)}:{max(user_a, user_b)}"
