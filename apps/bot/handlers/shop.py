from __future__ import annotations

from datetime import datetime
from typing import List

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.core.awards import create_bonus_award, try_unlock_bonuses
from apps.bot.core.wallets import add_coins_cash, get_wallet_balance
from apps.bot.infra.settings import get_settings
from apps.bot.repositories.purchases import record_purchase
from apps.bot.repositories.users import get_or_create_user
from apps.bot.services import referrals as referral_service, store

settings = get_settings()


def create_router() -> Router:
    router = Router(name="shop")

    def build_keyboard() -> InlineKeyboardMarkup:
        buttons: List[List[InlineKeyboardButton]] = []
        for package in store.list_packages():
            text = f"{package.title} — {package.price_xtr}★"
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=text,
                        callback_data=f"shop:buy:{package.id}",
                    )
                ]
            )
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @router.message(Command("buy"))
    async def handle_buy(message: Message, session: AsyncSession) -> None:
        if not settings.payments_enabled:
            await message.answer("Покупки временно недоступны")
            return
        if message.from_user:
            await get_or_create_user(session, message.from_user)
        await message.answer("Выбери пакет коинов:", reply_markup=build_keyboard())

    @router.callback_query(F.data.startswith("shop:buy:"))
    async def handle_buy_callback(call: CallbackQuery, session: AsyncSession) -> None:
        if not call.from_user:
            await call.answer()
            return
        if call.message is None:
            await call.answer("Нет сообщения для оформления", show_alert=True)
            return
        if not settings.payments_enabled:
            await call.answer("Недоступно", show_alert=True)
            return
        package_id = call.data.split(":")[-1]
        package = store.get_package(package_id)
        if package is None:
            await call.answer("Пакет не найден", show_alert=True)
            return
        await get_or_create_user(session, call.from_user)
        prices = [LabeledPrice(label=package.title, amount=package.price_xtr)]
        await call.message.answer_invoice(
            title=package.title,
            description=package.description,
            payload=package.payload,
            provider_token=settings.payment_provider_token,
            currency="XTR",
            prices=prices,
        )
        await call.answer()

    @router.pre_checkout_query()
    async def handle_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
        package = store.get_package_by_payload(pre_checkout_query.invoice_payload)
        if not settings.payments_enabled or package is None:
            await pre_checkout_query.answer(ok=False, error_message="Покупки недоступны")
            return
        await pre_checkout_query.answer(ok=True)

    @router.message(F.successful_payment)
    async def handle_successful_payment(message: Message, session: AsyncSession) -> None:
        payment = message.successful_payment
        if payment is None or message.from_user is None:
            return
        package = store.get_package_by_payload(payment.invoice_payload)
        if package is None:
            await message.answer("Не удалось определить пакет, обратитесь в поддержку")
            return
        user = await get_or_create_user(session, message.from_user)
        purchase, created = await record_purchase(
            session,
            user_id=user.id,
            charge_id=payment.provider_payment_charge_id,
            product_code=package.id,
            amount_xtr=payment.total_amount,
            coins_granted=package.coins,
            bonus_granted=package.bonus_coins,
        )
        if not created:
            await message.answer("Эта оплата уже была учтена")
            return

        await add_coins_cash(
            session,
            user.id,
            package.coins,
            reason="purchase",
            metadata={"charge_id": purchase.charge_id, "package": package.id},
        )

        if package.bonus_coins > 0:
            await create_bonus_award(
                session,
                user.id,
                kind=f"deposit_{package.id}",
                granted=package.bonus_coins,
                wr_mult=1.0,
                cap_cashout=package.bonus_coins,
            )

        if user.first_deposit_at is None:
            user.first_deposit_at = datetime.utcnow()
            await try_unlock_bonuses(session, user.id)
        await referral_service.try_activate_referral(session, user.id)

        wallet = await get_wallet_balance(session, user.id)
        await message.answer(
            f"Оплата успешна! +{package.coins} коинов.\n"
            f"Текущий баланс: {wallet.coins_cash} cash / {wallet.coins_bonus} bonus",
        )

    return router
