from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func, select

from apps.bot.core.wallets import add_coins_bonus, add_coins_cash, consume_coins, get_wallet
from apps.bot.db.models import BonusAward, BonusAwardStatus, TurnoverRule


async def create_bonus_award(
    session: AsyncSession,
    user_id: int,
    *,
    kind: str,
    granted: int,
    wr_mult: float,
    cap_cashout: int,
    expires_at: datetime | None = None,
) -> BonusAward:
    if granted <= 0:
        raise ValueError("granted must be positive")
    if cap_cashout <= 0:
        raise ValueError("cap_cashout must be positive")
    turnover_required = int(Decimal(granted) * Decimal(str(wr_mult)))
    if turnover_required <= 0:
        turnover_required = granted
    award = BonusAward(
        user_id=user_id,
        kind=kind,
        granted=granted,
        wr_mult=Decimal(str(wr_mult)),
        turnover_required=max(turnover_required, 0),
        cap_cashout=cap_cashout,
        status=BonusAwardStatus.ACTIVE.value,
        expires_at=expires_at,
    )
    session.add(award)
    await session.flush()
    await add_coins_bonus(session, user_id, granted, award_id=award.id, reason=f"bonus_{kind}")
    return award


async def apply_turnover(session: AsyncSession, user_id: int, game: str, stake: int) -> int:
    if stake <= 0:
        return 0

    rule = await session.scalar(select(TurnoverRule.contribution).where(TurnoverRule.game == game))
    if rule is None or rule <= 0:
        return 0

    contribution = int(stake * rule / 100)
    if contribution <= 0:
        contribution = stake if rule > 0 else 0
    if contribution <= 0:
        return 0

    awards = (
        await session.scalars(
            select(BonusAward).where(
                BonusAward.user_id == user_id,
                BonusAward.status.in_([BonusAwardStatus.ACTIVE.value, BonusAwardStatus.READY.value]),
            )
        )
    ).all()

    applied_total = 0
    for award in awards:
        remaining = award.turnover_required - award.turnover_progress
        if remaining <= 0:
            award.status = BonusAwardStatus.READY.value
            continue
        delta = min(remaining, contribution)
        award.turnover_progress += delta
        applied_total += delta
        if award.turnover_progress >= award.turnover_required:
            award.status = BonusAwardStatus.READY.value

    return applied_total


async def try_unlock_bonuses(session: AsyncSession, user_id: int) -> dict:
    wallet = await get_wallet(session, user_id, for_update=True)
    unlocked: list[dict[str, int]] = []

    awards = (
        await session.scalars(
            select(BonusAward).where(
                BonusAward.user_id == user_id,
                BonusAward.status == BonusAwardStatus.READY.value,
            )
        )
    ).all()

    for award in awards:
        transferable = max(0, award.cap_cashout - award.cashed_out)
        if transferable == 0:
            award.status = BonusAwardStatus.COMPLETED.value
            continue
        available_bonus = wallet.coins_bonus
        transfer_amount = min(available_bonus, transferable)
        if transfer_amount <= 0:
            continue
        await consume_coins(
            session,
            user_id,
            transfer_amount,
            prefer="bonus_first",
            reason="bonus_unlock",
            metadata={"award_id": award.id},
        )
        await add_coins_cash(
            session,
            user_id,
            transfer_amount,
            reason="bonus_unlock",
            metadata={"award_id": award.id},
        )
        award.cashed_out += transfer_amount
        award.status = BonusAwardStatus.COMPLETED.value
        award.unlocked_at = datetime.utcnow()
        unlocked.append({"award_id": award.id, "transferred": transfer_amount})
        wallet = await get_wallet(session, user_id, for_update=True)

    return {"awards": unlocked}


async def user_has_locked_bonuses(session: AsyncSession, user_id: int) -> bool:
    stmt = select(func.count()).where(
        BonusAward.user_id == user_id,
        BonusAward.status.in_([BonusAwardStatus.ACTIVE.value, BonusAwardStatus.READY.value]),
    )
    total = await session.scalar(stmt)
    return bool(total)
