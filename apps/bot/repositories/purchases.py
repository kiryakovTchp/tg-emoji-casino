from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.db.models import Purchase


async def record_purchase(
    session: AsyncSession,
    *,
    user_id: int,
    charge_id: str,
    product_code: str,
    amount_xtr: int,
    coins_granted: int,
    bonus_granted: int,
) -> tuple[Purchase, bool]:
    existing = await session.scalar(select(Purchase).where(Purchase.charge_id == charge_id))
    if existing is not None:
        return existing, False

    purchase = Purchase(
        user_id=user_id,
        charge_id=charge_id,
        product_code=product_code,
        amount_xtr=amount_xtr,
        coins_granted=coins_granted,
        bonus_granted=bonus_granted,
        status="completed",
    )
    session.add(purchase)
    await session.flush()
    return purchase, True
