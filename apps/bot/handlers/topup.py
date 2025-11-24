from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.core.wallets import add_coins_bonus, add_coins_cash
from apps.bot.db.models import Payment
from apps.bot.infra.settings import get_settings
from apps.bot.repositories.users import get_or_create_user
from apps.bot.ui.errors import show_error_screen

settings = get_settings()
router = Router(name="topup")

# Configuration for packs
TOPUP_PACKS = {
    "mini": {
        "label": "Mini Pack",
        "stars_price": 1800,
        "cash_add": 1000,
        "bonus_add": 500,
    },
    "pro": {
        "label": "Pro Pack",
        "stars_price": 4800,
        "cash_add": 3000,
        "bonus_add": 2000,
    },
}


def topup_entry_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for pack_id, pack in TOPUP_PACKS.items():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{pack['label']} — {pack['stars_price']}⭐",
                    callback_data=f"topup_pack_{pack_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="casino:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topup_detail_keyboard(pack_id: str, stars_price: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"✅ Оплатить {stars_price}⭐",
                callback_data=f"topup_pay_{pack_id}",
            )
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="balance:topup")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "💳 Пополнить баланс")
@router.callback_query(F.data == "balance:topup")
async def handle_topup_entry(event: Message | CallbackQuery) -> None:
    text = (
        "💳 <b>Пополнение баланса</b>\n\n"
        "Ты пополняешь coins за ⭐ Stars через безопасный платёж в Telegram.\n\n"
        "Выбери пакет:"
    )
    markup = topup_entry_keyboard()

    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message:
            await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("topup_pack_"))
async def handle_pack_detail(call: CallbackQuery) -> None:
    pack_id = call.data.replace("topup_pack_", "")
    pack = TOPUP_PACKS.get(pack_id)

    if not pack:
        await show_error_screen(call, "ERR-GENERIC", error_id="pack_not_found")
        return

    await call.answer()
    text = (
        f"<b>{pack['label']}</b>\n\n"
        "Ты получишь:\n"
        f"• {pack['cash_add']} 💰 Cash\n"
        f"• {pack['bonus_add']} 🎁 Bonus\n\n"
        f"Цена: <b>{pack['stars_price']}⭐</b>"
    )
    markup = topup_detail_keyboard(pack_id, pack['stars_price'])
    
    if call.message:
        await call.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data.startswith("topup_pay_"))
async def handle_pay_init(call: CallbackQuery, session: AsyncSession) -> None:
    pack_id = call.data.replace("topup_pay_", "")
    pack = TOPUP_PACKS.get(pack_id)

    if not pack:
        await show_error_screen(call, "ERR-GENERIC", error_id="pack_not_found")
        return

    await call.answer("Открываю окно оплаты…")
    
    user = await get_or_create_user(session, call.from_user)
    invoice_payload = f"topup_{user.id}_{pack_id}_{uuid.uuid4().hex[:8]}"
    
    # Save pending payment
    payment = Payment(
        user_id=user.id,
        pack_id=pack_id,
        amount_stars=pack["stars_price"],
        amount_cash=pack["cash_add"],
        amount_bonus=pack["bonus_add"],
        invoice_payload=invoice_payload,
        state="WAITING",
    )
    session.add(payment)
    await session.commit()

    try:
        await call.message.answer_invoice(
            title=f"Пополнение: {pack['label']}",
            description=f"{pack['cash_add']} Cash + {pack['bonus_add']} Bonus",
            payload=invoice_payload,
            currency="XTR",
            prices=[LabeledPrice(label=pack["label"], amount=pack["stars_price"])],
            start_parameter=f"topup_{pack_id}",
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        await show_error_screen(call, "ERR-PAY-INV")


@router.pre_checkout_query()
async def handle_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message, session: AsyncSession) -> None:
    payment_data = message.successful_payment
    payload = payment_data.invoice_payload

    # Idempotency check
    # In a real app, we should query by payload. 
    # Since we don't have a direct repository method yet, we'll use a direct query or assume session is enough.
    # For simplicity in this iteration, we'll fetch the payment.
    
    from sqlalchemy import select
    stmt = select(Payment).where(Payment.invoice_payload == payload)
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()

    if not payment:
        # Payment not found? Log error
        print(f"Payment not found for payload: {payload}")
        return

    if payment.state == "SUCCESS":
        # Already processed
        return

    # Update payment state
    payment.state = "SUCCESS"
    payment.telegram_payment_charge_id = payment_data.telegram_payment_charge_id
    
    # Grant coins
    await add_coins_cash(session, payment.user_id, payment.amount_cash, reason="topup", metadata={"pack_id": payment.pack_id})
    await add_coins_bonus(session, payment.user_id, payment.amount_bonus, reason="topup", metadata={"pack_id": payment.pack_id})
    
    await session.commit()

    # Get updated balance
    from apps.bot.core.wallets import get_wallet_balance
    wallet = await get_wallet_balance(session, payment.user_id)

    text = (
        "✅ <b>Баланс пополнен!</b>\n\n"
        "Начислено:\n"
        f"• {payment.amount_cash} 💰 Cash\n"
        f"• {payment.amount_bonus} 🎁 Bonus\n\n"
        "Новый баланс:\n"
        f"💰 Cash: {wallet.coins_cash}\n"
        f"🎁 Bonus: {wallet.coins_bonus}"
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Играть в слот", callback_data="slot:open")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="casino:menu")],
    ])
    
    await message.answer(text, reply_markup=markup)
