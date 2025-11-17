from __future__ import annotations

from datetime import datetime

from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.core.awards import create_bonus_award
from apps.bot.core.wallets import add_coins_bonus, get_wallet
from apps.bot.db.models import User
from apps.bot.infra.settings import get_settings
from apps.bot.services import referrals as referral_service

settings = get_settings()


async def get_or_create_user(session: AsyncSession, tg_user: TgUser) -> User:
    user = await session.scalar(select(User).where(User.tg_id == tg_user.id))
    if user is None:
        user = User(
            tg_id=tg_user.id,
            username=tg_user.username,
            locale=tg_user.language_code,
            last_seen=datetime.utcnow(),
        )
        session.add(user)
        await session.flush()
        await _apply_new_user_rewards(session, user)
        await referral_service.ensure_ref_code(session, user)
    else:
        user.username = tg_user.username or user.username
        user.locale = tg_user.language_code or user.locale
        user.last_seen = datetime.utcnow()
        if settings.admin_id and tg_user.id == settings.admin_id:
            await _ensure_admin_balance(session, user)
        if not user.ref_code:
            await referral_service.ensure_ref_code(session, user)
    return user


async def upsert_telegram_user(
    session: AsyncSession,
    *,
    tg_id: int,
    username: str | None = None,
    first_name: str | None = None,
    language_code: str | None = None,
) -> User:
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None:
        user = User(
            tg_id=tg_id,
            username=username,
            locale=language_code,
            last_seen=datetime.utcnow(),
        )
        session.add(user)
        await session.flush()
        await _apply_new_user_rewards(session, user)
        await referral_service.ensure_ref_code(session, user)
    else:
        user.username = username or user.username
        user.locale = language_code or user.locale
        user.last_seen = datetime.utcnow()
        if settings.admin_id and tg_id == settings.admin_id:
            await _ensure_admin_balance(session, user)
        if not user.ref_code:
            await referral_service.ensure_ref_code(session, user)
    return user


async def _apply_new_user_rewards(session: AsyncSession, user: User) -> None:
    if settings.welcome_enabled and settings.welcome_bonus_coins > 0:
        wr = settings.wr_welcome if settings.bonus_wr_enabled else 1.0
        cap = int(settings.cap_welcome * settings.welcome_bonus_coins) or settings.welcome_bonus_coins
        await create_bonus_award(
            session,
            user.id,
            kind="welcome",
            granted=settings.welcome_bonus_coins,
            wr_mult=wr,
            cap_cashout=cap,
        )
    if settings.welcome_free_spins > 0:
        wallet = await get_wallet(session, user.id, for_update=True)
        wallet.free_spins_left += settings.welcome_free_spins
    if settings.admin_id and user.tg_id == settings.admin_id:
        await _ensure_admin_balance(session, user)


async def _ensure_admin_balance(session: AsyncSession, user: User) -> None:
    target_bonus = 10_000
    wallet = await get_wallet(session, user.id, for_update=True)
    missing = target_bonus - wallet.coins_bonus
    if missing > 0:
        await add_coins_bonus(session, user.id, missing, reason="admin_seed")
