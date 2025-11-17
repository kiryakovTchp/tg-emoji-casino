from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.repositories.users import get_or_create_user
from apps.bot.services.gifts import available_tiers, check_user_gift_status, redeem_gift

router = Router(name="gifts")


def gift_menu_keyboard(eligible: bool) -> InlineKeyboardMarkup:
    kb = []
    if eligible:
        for tier_key, tier in available_tiers().items():
            kb.append(
                [InlineKeyboardButton(text=f"{tier['label']} ({tier['bonus_cost']} bonus)", callback_data=f"gifts:redeem:{tier_key}")]
            )
    kb.append([InlineKeyboardButton(text="⬅ Назад", callback_data="casino:menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


async def render_gifts(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    user = await get_or_create_user(session, message.from_user)
    eligible, reason = await check_user_gift_status(session, user)
    tiers = available_tiers()
    if not tiers:
        text = "Сейчас обмен подарков отключён."
    elif eligible:
        text = "Выберите подарок для обмена:"
    else:
        text = f"Подарки недоступны: {reason}"
    markup = gift_menu_keyboard(eligible and bool(tiers))
    if message.edit_date:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "gifts:open")
async def handle_open(call: CallbackQuery, session: AsyncSession) -> None:
    await call.answer()
    if call.message:
        await render_gifts(call.message, session)


@router.callback_query(F.data.startswith("gifts:redeem:"))
async def handle_redeem(call: CallbackQuery, session: AsyncSession) -> None:
    if not call.from_user or not call.message:
        return
    tier = call.data.split(":")[-1]
    user = await get_or_create_user(session, call.from_user)
    success, message_text = await redeem_gift(session, user, tier)
    await session.commit()
    await call.answer(message_text, show_alert=not success)
    await render_gifts(call.message, session)
