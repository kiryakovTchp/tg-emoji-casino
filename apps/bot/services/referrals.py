from __future__ import annotations

import random
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.core.awards import create_bonus_award
from apps.bot.db.models import Referral, User
from apps.bot.infra.settings import get_settings

settings = get_settings()
REF_CODE_LENGTH = 6
MIN_SPINS_FOR_REFERRAL = 10
MIN_CRASH_BETS_FOR_REFERRAL = 1


def _generate_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=REF_CODE_LENGTH))


async def ensure_ref_code(session: AsyncSession, user: User) -> str:
    if user.ref_code:
        return user.ref_code
    while True:
        candidate = _generate_code()
        exists = await session.scalar(select(User.id).where(User.ref_code == candidate))
        if not exists:
            user.ref_code = candidate
            await session.flush()
            return candidate


async def register_invite(session: AsyncSession, invitee: User, code: str) -> None:
    inviter = await session.scalar(select(User).where(User.ref_code == code))
    if inviter is None or inviter.id == invitee.id:
        return
    # ensure invitee has not been attached already
    existing = await session.scalar(select(Referral).where(Referral.invitee_id == invitee.id))
    if existing is not None:
        return
    referral = Referral(ref_code=code, inviter_id=inviter.id, invitee_id=invitee.id)
    session.add(referral)
    await session.flush()


async def try_activate_referral(session: AsyncSession, invitee_id: int) -> None:
    referral = await session.scalar(select(Referral).where(Referral.invitee_id == invitee_id))
    if referral is None or referral.activated:
        return
    invitee = await session.get(User, invitee_id)
    if invitee is None or invitee.first_deposit_at is None:
        return
    if invitee.paid_spins_count < MIN_SPINS_FOR_REFERRAL and invitee.paid_crash_bets_count < MIN_CRASH_BETS_FOR_REFERRAL:
        return
    await grant_referral_reward(session, referral.inviter_id)
    referral.activated = True
    referral.activated_at = invitee.first_deposit_at
    await session.flush()


async def grant_referral_reward(session: AsyncSession, inviter_id: int) -> None:
    reward = settings.referral_bonus_coins
    if reward <= 0:
        return
    award_id = await create_bonus_award(
        session,
        user_id=inviter_id,
        kind="referral",
        granted=reward,
        wr_mult=settings.referral_wr,
        cap_cashout=settings.referral_cap,
    )
    # create_bonus_award already credits bonus via wallet service
    return
