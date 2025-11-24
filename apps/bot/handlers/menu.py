from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.core.events import track_event
from apps.bot.core.slot_payouts import bonus_bet_limit, get_slot_payouts
from apps.bot.core.wallets import (
    InsufficientFunds,
    add_coins_bonus,
    add_coins_cash,
    consume_coins,
    get_wallet,
    get_wallet_balance,
)
from apps.bot.db.models import Spin
from apps.bot.infra.settings import get_settings
from apps.bot.repositories.users import get_or_create_user
from apps.bot.services import referrals as referral_service

settings = get_settings()
payouts = get_slot_payouts()

MIN_BET = 10
MAX_BET = 50_000
SLOT_STATE_TTL = 60 * 60 * 24 * 7
DEFAULT_SLOT_STATE = {"bet": 100, "mode": "cash", "last": None}


def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎰 Слот", callback_data="slot:open"), InlineKeyboardButton(text="⚔️ Дуэли", callback_data="duels:open")],
        [InlineKeyboardButton(text="🚀 Crash", callback_data="crash:open"), InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="balance:topup")],
        [InlineKeyboardButton(text="🎁 Подарки", callback_data="gifts:open"), InlineKeyboardButton(text="👤 Профиль", callback_data="profile:open")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slot_keyboard(state: dict[str, Any]) -> InlineKeyboardMarkup:
    mode_label = "Режим: Coins" if state.get("mode") == "cash" else "Режим: Bonus"
    rows = [
        [
            InlineKeyboardButton(text="-10", callback_data="slot:bet:dec:10"),
            InlineKeyboardButton(text="-100", callback_data="slot:bet:dec:100"),
            InlineKeyboardButton(text="+10", callback_data="slot:bet:inc:10"),
            InlineKeyboardButton(text="+100", callback_data="slot:bet:inc:100"),
        ],
        [InlineKeyboardButton(text=mode_label, callback_data="slot:toggle_mode")],
        [InlineKeyboardButton(text="Крутить 🎰", callback_data="slot:spin")],
        [InlineKeyboardButton(text="⬅ Главное меню", callback_data="casino:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slot_state_key(user_id: int) -> str:
    return f"slot:state:{user_id}"


def format_slot_text(state: dict[str, Any], *, wallet) -> str:
    mode = state.get("mode", "cash")
    last = state.get("last")
    lines = [
        "🎰 Слот",
        f"Режим: {'Coins' if mode == 'cash' else 'Bonus'}",
        f"Ставка: {state.get('bet', 0)}",
        f"Баланс: {wallet.coins_cash} cash / {wallet.coins_bonus} bonus",
    ]
    if last:
        symbols = last.get("symbols", [])
        lines.append(
            f"Последний спин: {''.join(symbols)} x{last.get('multiplier', 0)} → {last.get('payout', 0)}"
        )
    return "\n".join(lines)


async def load_slot_state(redis: Redis, user_id: int) -> dict[str, Any]:
    raw = await redis.get(slot_state_key(user_id))
    if raw:
        return json.loads(raw)
    state = DEFAULT_SLOT_STATE.copy()
    await save_slot_state(redis, user_id, state)
    return state


async def save_slot_state(redis: Redis, user_id: int, state: dict[str, Any]) -> None:
    await redis.set(slot_state_key(user_id), json.dumps(state), ex=SLOT_STATE_TTL)


async def render_main_menu(message: Message) -> None:
    if message.edit_date:
        await message.edit_text("Главное меню", reply_markup=main_menu_keyboard())
    else:
        await message.answer("Главное меню", reply_markup=main_menu_keyboard())


async def render_slot(message: Message, wallet, state: dict[str, Any], notice: str | None = None) -> None:
    text = format_slot_text(state, wallet=wallet)
    if notice:
        text = f"{text}\n\n{notice}"
    if message.edit_date:
        await message.edit_text(text, reply_markup=slot_keyboard(state))
    else:
        await message.answer(text, reply_markup=slot_keyboard(state))


def create_router() -> Router:
    router = Router(name="menu")

    @router.message(CommandStart())
    async def handle_start(message: Message, session: AsyncSession) -> None:
        if not message.from_user:
            return
        user = await get_or_create_user(session, message.from_user)
        await referral_service.ensure_ref_code(session, user)
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            arg = parts[1].strip()
            if arg.lower().startswith("ref_"):
                code = arg[4:].upper()
                await referral_service.register_invite(session, user, code)
        await message.answer("Главное меню", reply_markup=main_menu_keyboard())

    @router.message(Command("profile"))
    async def handle_profile(message: Message, session: AsyncSession) -> None:
        if not message.from_user:
            return
        user = await get_or_create_user(session, message.from_user)
        code = await referral_service.ensure_ref_code(session, user)
        bot_info = await message.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ref_{code}"
        wallet = await get_wallet_balance(session, user.id)
        text = (
            f"Баланс: {wallet.coins_cash} cash / {wallet.coins_bonus} bonus\\n"
            f"Твой код: <b>{code}</b>\\n"
            f"Ссылка: {link}\\n"
            "За друга, который пополнит и сыграет, ты получишь бонусы."
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Скопировать ссылку", url=link)]]
        )
        await message.answer(text, reply_markup=markup)

    @router.callback_query(F.data == "casino:menu")
    async def handle_menu(call: CallbackQuery) -> None:
        await call.answer()
        if call.message:
            await render_main_menu(call.message)



    @router.callback_query(F.data == "slot:open")
    async def handle_slot_open(call: CallbackQuery, session: AsyncSession, redis: Redis) -> None:
        await call.answer()
        if not call.from_user or not call.message:
            return
        try:
            user = await get_or_create_user(session, call.from_user)
            state = await load_slot_state(redis, call.from_user.id)
            wallet = await get_wallet_balance(session, user.id)
            await render_slot(call.message, wallet, state)
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Error in slot:open: {error_trace}")
            await call.message.answer(f"Ошибка при открытии слота: {e}")

    @router.callback_query(F.data.startswith("slot:bet:"))
    async def handle_slot_bet(call: CallbackQuery, session: AsyncSession, redis: Redis) -> None:
        if not call.from_user or not call.message:
            return
        await call.answer()
        user = await get_or_create_user(session, call.from_user)
        parts = call.data.split(":")
        direction = parts[2]
        step = int(parts[3])
        state = await load_slot_state(redis, call.from_user.id)
        delta = step if direction == "inc" else -step
        new_bet = max(MIN_BET, min(MAX_BET, state.get("bet", MIN_BET) + delta))
        state["bet"] = new_bet
        await save_slot_state(redis, call.from_user.id, state)
        wallet = await get_wallet_balance(session, user.id)
        await render_slot(call.message, wallet, state)

    @router.callback_query(F.data == "slot:toggle_mode")
    async def handle_slot_toggle(call: CallbackQuery, session: AsyncSession, redis: Redis) -> None:
        if not call.from_user or not call.message:
            return
        await call.answer()
        user = await get_or_create_user(session, call.from_user)
        state = await load_slot_state(redis, call.from_user.id)
        state["mode"] = "bonus" if state.get("mode") == "cash" else "cash"
        await save_slot_state(redis, call.from_user.id, state)
        wallet = await get_wallet_balance(session, user.id)
        await render_slot(call.message, wallet, state)

    @router.callback_query(F.data == "slot:spin")
    async def handle_slot_spin(call: CallbackQuery, session: AsyncSession, redis: Redis) -> None:
        if not call.from_user or not call.message:
            return
        user = await get_or_create_user(session, call.from_user)
        lock = redis.lock(f"slot:lock:{call.from_user.id}", timeout=5)
        acquired = await lock.acquire(blocking=False)
        if not acquired:
            await call.answer("Спин уже выполняется", show_alert=True)
            return

        try:
            await call.answer()
            state = await load_slot_state(redis, user.id)
            bet = int(state.get("bet", MIN_BET))
            mode = state.get("mode", "cash")
            wallet = await get_wallet(session, user.id, for_update=True)

            if bet < MIN_BET:
                bet = MIN_BET

            if mode == "bonus":
                limit = bonus_bet_limit(wallet.coins_bonus)
                if limit <= 0 or bet > limit:
                    await call.message.answer(
                        f"Бонусная ставка ограничена {limit} коинами. Уменьшите ставку."
                    )
                    return

            try:
                consumption = await consume_coins(
                    session,
                    user.id,
                    bet,
                    prefer="cash_first" if mode == "cash" else "bonus_first",
                    reason="slot_bet",
                )
            except InsufficientFunds:
                await call.message.answer("Недостаточно средств для ставки")
                return

            await track_event(
                session,
                user_id=user.id,
                name="slot_spin",
                props={"bet": bet, "mode": mode, "cash": consumption.cash, "bonus": consumption.bonus},
            )

            if consumption.cash > 0:
                user.paid_spins_count += 1
                await referral_service.try_activate_referral(session, user.id)

            dice_message = await call.message.answer_dice(emoji="🎰")
            dice_value = dice_message.dice.value if dice_message.dice else 0
            payout_amount, outcome = payouts.calc_payout(dice_value, bet)

            payout_cash = 0
            payout_bonus = 0
            if payout_amount > 0:
                if consumption.cash and not consumption.bonus:
                    payout_cash = payout_amount
                    await add_coins_cash(
                        session,
                        user.id,
                        payout_cash,
                        reason="slot_win",
                        metadata={"dice_value": dice_value},
                    )
                else:
                    payout_bonus = payout_amount
                    await add_coins_bonus(
                        session,
                        user.id,
                        payout_bonus,
                        reason="slot_win",
                        metadata={"dice_value": dice_value},
                    )

            spin = Spin(
                user_id=user.id,
                bet_coins_cash=consumption.cash,
                bet_coins_bonus=consumption.bonus,
                dice_value=dice_value,
                symbols=outcome.symbols,
                multiplier=Decimal(str(outcome.multiplier)),
                payout_cash=payout_cash,
                payout_bonus=payout_bonus,
            )
            session.add(spin)

            await track_event(
                session,
                user_id=user.id,
                name="slot_result",
                props={
                    "bet": bet,
                    "mode": mode,
                    "dice_value": dice_value,
                    "multiplier": outcome.multiplier,
                    "payout": payout_amount,
                },
            )

            state["last"] = {
                "symbols": outcome.symbols,
                "multiplier": outcome.multiplier,
                "payout": payout_amount,
            }
            await save_slot_state(redis, user.id, state)
            wallet_after = await get_wallet_balance(session, user.id)
            notice = (
                f"Выпало {''.join(outcome.symbols)} x{outcome.multiplier}. "
                f"{'Выигрыш' if payout_amount else 'Проигрыш'}: {payout_amount}."
            )
            await render_slot(call.message, wallet_after, state, notice=notice)
        finally:
            await lock.release()

    return router
