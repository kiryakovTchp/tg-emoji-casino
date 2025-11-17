from __future__ import annotations

from datetime import datetime, date
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.core.awards import user_has_locked_bonuses
from apps.bot.core.wallets import InsufficientFunds, consume_coins
from apps.bot.db.models import Gift, GiftStatus, TreasuryState, User
from apps.bot.infra.settings import get_settings

settings = get_settings()


def available_tiers() -> Dict[str, dict]:
    tiers: Dict[str, dict] = {}
    if settings.gift_small_cost_bonus > 0 and settings.gift_small_cost_xtr > 0:
        tiers["small"] = {
            "label": "Small",
            "bonus_cost": settings.gift_small_cost_bonus,
            "xtr_cost": settings.gift_small_cost_xtr,
        }
    if settings.gift_medium_cost_bonus > 0 and settings.gift_medium_cost_xtr > 0:
        tiers["medium"] = {
            "label": "Medium",
            "bonus_cost": settings.gift_medium_cost_bonus,
            "xtr_cost": settings.gift_medium_cost_xtr,
        }
    if settings.gift_big_cost_bonus > 0 and settings.gift_big_cost_xtr > 0:
        tiers["big"] = {
            "label": "Big",
            "bonus_cost": settings.gift_big_cost_bonus,
            "xtr_cost": settings.gift_big_cost_xtr,
        }
    return tiers


async def get_treasury(session: AsyncSession, *, for_update: bool = False) -> TreasuryState:
    treasury = await session.get(TreasuryState, 1, with_for_update=for_update)
    if treasury is None:
        treasury = TreasuryState(id=1, current_xtr=settings.treasury_xtr_start)
        session.add(treasury)
        await session.flush()
    return treasury


async def check_user_gift_status(session: AsyncSession, user: User) -> tuple[bool, str]:
    if user.first_deposit_at is None:
        return False, "Требуется хотя бы один депозит"
    if await user_has_locked_bonuses(session, user.id):
        return False, "Завершите отыгрыш бонусов"
    return True, "Доступно к обмену"


async def redeem_gift(session: AsyncSession, user: User, tier: str) -> tuple[bool, str]:
    tiers = available_tiers()
    tier_data = tiers.get(tier)
    if tier_data is None:
        return False, "Тир недоступен"

    eligible, reason = await check_user_gift_status(session, user)
    if not eligible:
        return False, reason

    treasury = await get_treasury(session, for_update=True)
    today = date.today()
    if treasury.budget_spent_date is None or treasury.budget_spent_date.date() != today:
        treasury.budget_spent_date = datetime.utcnow()
        treasury.budget_spent_xtr = 0

    gift_cost_xtr = tier_data["xtr_cost"]
    gift_cost_bonus = tier_data["bonus_cost"]

    if treasury.budget_spent_xtr + gift_cost_xtr > settings.gifts_budget_xtr_day:
        gift = Gift(
            user_id=user.id,
            tier=tier,
            bonus_cost=gift_cost_bonus,
            xtr_cost=gift_cost_xtr,
            status=GiftStatus.QUEUED.value,
            payload={"reason": "budget"},
        )
        session.add(gift)
        await session.flush()
        return False, "Дневной лимит исчерпан. Заявка в очереди"

    projected_liability = treasury.gift_liability + gift_cost_xtr
    available = treasury.current_xtr - projected_liability
    if available < settings.treasury_floor_xtr:
        gift = Gift(
            user_id=user.id,
            tier=tier,
            bonus_cost=gift_cost_bonus,
            xtr_cost=gift_cost_xtr,
            status=GiftStatus.QUEUED.value,
            payload={"reason": "treasury_floor"},
        )
        session.add(gift)
        await session.flush()
        return False, "Казна временно недоступна, заявка в очереди"

    try:
        await consume_coins(
            session,
            user.id,
            gift_cost_bonus,
            prefer="bonus_first",
            reason="gift_redeem",
        )
    except InsufficientFunds:
        return False, "Недостаточно бонусов"

    treasury.gift_liability = projected_liability
    treasury.budget_spent_xtr += gift_cost_xtr

    gift = Gift(
        user_id=user.id,
        tier=tier,
        bonus_cost=gift_cost_bonus,
        xtr_cost=gift_cost_xtr,
        status=GiftStatus.PENDING.value,
    )
    session.add(gift)
    await session.flush()
    return True, "Заявка создана, скоро отправим подарок"
