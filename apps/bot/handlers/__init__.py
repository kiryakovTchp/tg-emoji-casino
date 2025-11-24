from __future__ import annotations

from aiogram import Dispatcher

from . import duels, gifts, menu, topup


def register_handlers(dp: Dispatcher) -> None:
    dp.include_router(menu.create_router())
    dp.include_router(topup.router)
    dp.include_router(gifts.router)
    dp.include_router(duels.router)
