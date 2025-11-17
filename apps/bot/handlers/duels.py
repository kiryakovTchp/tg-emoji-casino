from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.core.wallets import InsufficientFunds, add_coins_bonus, add_coins_cash, consume_coins
from apps.bot.db.models import User
from apps.bot.infra.settings import get_settings
from apps.bot.repositories.users import get_or_create_user
from apps.bot.services import duels

router = Router(name="duels")
settings = get_settings()

MIN_DUEL_STAKE = 50
MAX_DUEL_STAKE = 50_000


def duel_keyboard(duel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Принять", callback_data=f"duel:accept:{duel_id}")],
            [InlineKeyboardButton(text="Отменить", callback_data=f"duel:cancel:{duel_id}")],
        ]
    )


@router.message(Command("duel"))
async def command_duel(message: Message, session: AsyncSession) -> None:
    if message.chat.type not in {"group", "supergroup"}:
        await message.reply("Дуэли доступны только в группах")
        return
    if not message.from_user:
        return

    args = message.text.split()[1:]
    amount = MIN_DUEL_STAKE
    currency = "cash"
    if args:
        try:
            amount = int(args[0])
            if len(args) > 1:
                currency = args[1].lower()
        except ValueError:
            currency = args[0].lower()
            if len(args) > 1:
                amount = int(args[1])
    if currency not in {"cash", "bonus"}:
        currency = "cash"
    amount = max(MIN_DUEL_STAKE, min(MAX_DUEL_STAKE, amount))

    starter = await get_or_create_user(session, message.from_user)
    if await duels.user_has_active_duel(session, starter.id):
        await message.reply("У вас уже есть активная дуэль")
        return

    duel = await duels.create_duel(
        session,
        chat_id=message.chat.id,
        starter_id=starter.id,
        stake_amount=amount,
        stake_currency=currency,
    )
    mention = message.from_user.mention_html()
    text = (
        f"{mention} вызывает на дуэль!\n"
        f"Ставка: {amount} {'coins' if currency=='cash' else 'bonus'}\n"
        "Нажмите Принять, чтобы вступить."
    )
    sent = await message.reply(text, reply_markup=duel_keyboard(duel.id))
    await duels.mark_message(session, duel, message_id=sent.message_id, thread_id=sent.message_thread_id)
    await session.commit()


@router.callback_query(F.data.startswith("duel:cancel:"))
async def handle_duel_cancel(call: CallbackQuery, session: AsyncSession) -> None:
    if not call.from_user:
        return
    duel_id = int(call.data.split(":")[-1])
    duel = await duels.get_duel(session, duel_id, for_update=True)
    if duel is None:
        await call.answer("Дуэль не найдена", show_alert=True)
        return
    if duel.state != duels.DuelState.PENDING.value:
        await call.answer("Дуэль уже началась", show_alert=True)
        return
    starter = await get_or_create_user(session, call.from_user)
    if duel.starter_id != starter.id:
        await call.answer("Только автор может отменить дуэль", show_alert=True)
        return
    await duels.cancel_duel(session, duel)
    await session.commit()
    await call.answer("Дуэль отменена")
    if call.message:
        await call.message.edit_text("Дуэль отменена")


@router.callback_query(F.data.startswith("duel:accept:"))
async def handle_duel_accept(call: CallbackQuery, session: AsyncSession) -> None:
    if not call.from_user or not call.message:
        return
    duel_id = int(call.data.split(":")[-1])
    duel = await duels.get_duel(session, duel_id, for_update=True)
    if duel is None:
        await call.answer("Дуэль не найдена", show_alert=True)
        return
    if duel.state != duels.DuelState.PENDING.value:
        await call.answer("Дуэль уже не активна", show_alert=True)
        return
    opponent = await get_or_create_user(session, call.from_user)
    if duel.starter_id == opponent.id:
        await call.answer("Нельзя принять собственный вызов", show_alert=True)
        return
    if await duels.user_has_active_duel(session, opponent.id):
        await call.answer("У вас уже есть дуэль", show_alert=True)
        return

    starter = await session.get(User, duel.starter_id)
    if starter is None:
        await call.answer("Автор дуэли недоступен", show_alert=True)
        return

    prefer = "cash_first" if duel.stake_currency == "cash" else "bonus_first"
    if not await duels.can_start_pair(session, starter.id, opponent.id):
        await call.answer("Лимит дуэлей между вами на сегодня исчерпан", show_alert=True)
        return

    try:
        starter_spend = await consume_coins(session, starter.id, duel.stake_amount, prefer=prefer, reason="duel_stake")
    except InsufficientFunds:
        await duels.cancel_duel(session, duel)
        await session.commit()
        await call.answer("У автора дуэли недостаточно средств", show_alert=True)
        if call.message:
            await call.message.edit_text("Дуэль отменена: у автора нет средств")
        return
    try:
        opponent_spend = await consume_coins(session, opponent.id, duel.stake_amount, prefer=prefer, reason="duel_stake")
    except InsufficientFunds:
        await duels.cancel_duel(session, duel)
        if starter_spend.cash:
            await add_coins_cash(session, starter.id, starter_spend.cash, reason="duel_refund")
        if starter_spend.bonus:
            await add_coins_bonus(session, starter.id, starter_spend.bonus, reason="duel_refund")
        await session.commit()
        await call.answer("Недостаточно средств", show_alert=True)
        if call.message:
            await call.message.edit_text("Дуэль отменена: нет средств у оппонента")
        return

    duel.opponent_id = opponent.id
    duel.state = duels.DuelState.RUNNING.value
    duel.accepted_at = datetime.utcnow()
    duel.pair_key = duels.build_pair_key(starter.id, opponent.id)
    duel.bank_cash = starter_spend.cash + opponent_spend.cash
    duel.bank_bonus = starter_spend.bonus + opponent_spend.bonus
    duel.rounds = []
    await session.commit()

    await call.answer("Дуэль принята")
    if call.message:
        await call.message.edit_text("Дуэль началась!", reply_markup=None)

    await play_duel(call.message, session, duel, starter_id=starter.id, opponent_id=opponent.id)


async def play_duel(base_message: Message, session: AsyncSession, duel, *, starter_id: int, opponent_id: int) -> None:
    bot = base_message.bot
    chat_id = base_message.chat.id
    wins_starter = 0
    wins_opponent = 0
    round_num = 1
    rounds = []

    while wins_starter < 2 and wins_opponent < 2:
        await bot.send_message(chat_id, f"Раунд {round_num}. Бросаем кубики!", reply_to_message_id=base_message.message_id)
        starter_roll = await bot.send_dice(chat_id, emoji="🎰", reply_to_message_id=base_message.message_id)
        opponent_roll = await bot.send_dice(chat_id, emoji="🎰", reply_to_message_id=base_message.message_id)
        starter_value = starter_roll.dice.value if starter_roll.dice else 0
        opponent_value = opponent_roll.dice.value if opponent_roll.dice else 0
        if starter_value == opponent_value:
            await bot.send_message(chat_id, "Ничья в раунде, повторяем!", reply_to_message_id=base_message.message_id)
            continue
        if starter_value > opponent_value:
            wins_starter += 1
            winner_round = starter_id
        else:
            wins_opponent += 1
            winner_round = opponent_id
        rounds.append(
            {
                "round": round_num,
                "starter": starter_value,
                "opponent": opponent_value,
                "winner_id": winner_round,
            }
        )
        duel.rounds = rounds
        duel.wins_starter = wins_starter
        duel.wins_opponent = wins_opponent
        await session.commit()
        await bot.send_message(
            chat_id,
            f"Раунд {round_num} завершён. Счёт {wins_starter}:{wins_opponent}",
            reply_to_message_id=base_message.message_id,
        )
        round_num += 1

    winner_id = starter_id if wins_starter > wins_opponent else opponent_id
    payout_text = ""
    if duel.bank_cash > 0:
        await add_coins_cash(session, winner_id, duel.bank_cash, reason="duel_win", metadata={"duel_id": duel.id})
        payout_text = f"+{duel.bank_cash} coins"
    if duel.bank_bonus > 0:
        await add_coins_bonus(session, winner_id, duel.bank_bonus, reason="duel_win", metadata={"duel_id": duel.id})
        payout_text = f"+{duel.bank_bonus} bonus"

    duel.state = duels.DuelState.FINISHED.value
    duel.winner_id = winner_id
    duel.finished_at = datetime.utcnow()
    await session.commit()

    await bot.send_message(chat_id, f"Дуэль завершена! Победитель <a href='tg://user?id={winner_id}'>игрок</a> {payout_text}")
