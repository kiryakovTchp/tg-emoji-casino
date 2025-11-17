from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.db.models import BonusAward, BonusAwardStatus, Ledger, Wallet

Currency = Literal["coins_cash", "coins_bonus"]


class WalletError(Exception):
    pass


class InsufficientFunds(WalletError):
    pass


@dataclass
class WalletConsumption:
    cash: int
    bonus: int

    def to_dict(self) -> dict[str, int]:
        return {"cash": self.cash, "bonus": self.bonus}


async def _get_or_create_wallet(session: AsyncSession, user_id: int, *, for_update: bool = False) -> Wallet:
    wallet = await session.get(Wallet, user_id, with_for_update=for_update)
    if wallet is None:
        wallet = Wallet(user_id=user_id)
        session.add(wallet)
        await session.flush()
    return wallet


async def _add_ledger_entry(
    session: AsyncSession,
    user_id: int,
    currency: Currency,
    amount: int,
    reason: str,
    *,
    award_id: int | None = None,
    metadata: dict | None = None,
) -> None:
    entry = Ledger(
        user_id=user_id,
        currency=currency,
        amount=amount,
        reason=reason,
        award_id=award_id,
        payload=metadata,
    )
    session.add(entry)


async def add_coins_cash(
    session: AsyncSession,
    user_id: int,
    amount: int,
    *,
    reason: str = "credit",
    metadata: dict | None = None,
) -> int:
    if amount <= 0:
        raise ValueError("amount must be positive")
    wallet = await _get_or_create_wallet(session, user_id, for_update=True)
    wallet.coins_cash += amount
    await _add_ledger_entry(session, user_id, "coins_cash", amount, reason, metadata=metadata)
    return wallet.coins_cash


async def add_coins_bonus(
    session: AsyncSession,
    user_id: int,
    amount: int,
    *,
    award_id: int | None = None,
    reason: str = "bonus_credit",
    metadata: dict | None = None,
) -> int:
    if amount <= 0:
        raise ValueError("amount must be positive")
    wallet = await _get_or_create_wallet(session, user_id, for_update=True)
    wallet.coins_bonus += amount
    await _add_ledger_entry(
        session,
        user_id,
        "coins_bonus",
        amount,
        reason,
        award_id=award_id,
        metadata=metadata,
    )
    return wallet.coins_bonus


async def _has_active_bonus(session: AsyncSession, user_id: int) -> bool:
    result = await session.scalar(
        select(BonusAward.id).where(
            BonusAward.user_id == user_id,
            BonusAward.status.in_([BonusAwardStatus.ACTIVE.value, BonusAwardStatus.READY.value]),
        )
    )
    return result is not None


async def consume_coins(
    session: AsyncSession,
    user_id: int,
    amount: int,
    *,
    prefer: Literal["cash_first", "bonus_first", "auto_bonus_when_active"] = "cash_first",
    reason: str = "bet",
    metadata: dict | None = None,
) -> WalletConsumption:
    if amount <= 0:
        raise ValueError("amount must be positive")

    wallet = await _get_or_create_wallet(session, user_id, for_update=True)
    available_total = wallet.coins_cash + wallet.coins_bonus
    if available_total < amount:
        raise InsufficientFunds("not enough coins")

    use_bonus_first = False
    if prefer == "bonus_first":
        use_bonus_first = True
    elif prefer == "auto_bonus_when_active":
        use_bonus_first = await _has_active_bonus(session, user_id)
    elif prefer != "cash_first":
        raise ValueError("unknown prefer value")

    bonus_used = 0
    cash_used = 0

    if use_bonus_first:
        bonus_used = min(wallet.coins_bonus, amount)
        amount -= bonus_used
    cash_used = min(wallet.coins_cash, amount)
    amount -= cash_used

    if amount > 0:  # still need more coins, fallback to remaining source
        extra_bonus = min(wallet.coins_bonus - bonus_used, amount)
        bonus_used += extra_bonus
        amount -= extra_bonus

    if amount != 0:
        # Should never happen because of available_total check
        raise InsufficientFunds("not enough coins")

    wallet.coins_cash -= cash_used
    wallet.coins_bonus -= bonus_used

    if cash_used:
        await _add_ledger_entry(session, user_id, "coins_cash", -cash_used, reason, metadata=metadata)
    if bonus_used:
        await _add_ledger_entry(session, user_id, "coins_bonus", -bonus_used, reason, metadata=metadata)

    return WalletConsumption(cash=cash_used, bonus=bonus_used)


async def get_wallet(session: AsyncSession, user_id: int, *, for_update: bool = False) -> Wallet:
    return await _get_or_create_wallet(session, user_id, for_update=for_update)


async def get_wallet_balance(session: AsyncSession, user_id: int) -> Wallet:
    return await get_wallet(session, user_id, for_update=False)
