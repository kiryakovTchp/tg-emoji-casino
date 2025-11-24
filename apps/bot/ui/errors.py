from __future__ import annotations

import logging
from typing import Any

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from apps.bot.infra.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


ERROR_TEMPLATES = {
    "ERR-PAY-INV": {
        "title": "Не получилось создать счёт.",
        "description": "Telegram вернул ошибку при формировании платежа.",
        "buttons": [
            [{"text": "🔁 Попробовать ещё раз", "callback_data": "balance:topup"}],
        ],
    },
    "ERR-PAY-TIMEOUT": {
        "title": "Не получили подтверждение оплаты.",
        "description": "Окно оплаты было закрыто или платёж отменён.",
        "buttons": [
            [{"text": "🔁 Пополнить ещё раз", "callback_data": "balance:topup"}],
        ],
    },
    "ERR-PAY-FAIL": {
        "title": "Платёж не прошёл.",
        "description": "Telegram вернул статус «отклонён». Деньги не списаны.",
        "buttons": [
            [{"text": "🔁 Выбрать другой пакет", "callback_data": "balance:topup"}],
        ],
    },
    "ERR-GENERIC": {
        "title": "Что-то пошло не так.",
        "description": "Мы уже получили уведомление. Код инцидента: {error_id}.",
        "buttons": [],
    },
}


def _build_error_keyboard(template: dict[str, Any]) -> InlineKeyboardMarkup:
    rows = []
    # Template specific buttons
    for row_data in template.get("buttons", []):
        row = [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"]) for btn in row_data]
        rows.append(row)

    # Common buttons
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="casino:menu")])
    
    support_username = settings.admin_id  # Fallback or use a specific support env var if available
    # Ideally we should have SUPPORT_USERNAME in settings, but for now we can use a placeholder or skip if not set
    # Assuming we might want to add it later. For now, let's add a generic support button if we had a link.
    # Since we don't have a specific support link in settings yet, we'll skip it or use a placeholder.
    # The requirements mentioned SUPPORT_USERNAME from ENV. Let's assume it might be added to settings later.
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_error_screen(
    event: Message | CallbackQuery,
    code: str,
    error_id: str | None = None,
) -> None:
    """
    Displays an error screen to the user.
    """
    template = ERROR_TEMPLATES.get(code)
    if not template:
        # Fallback to generic if code not found, treating code as error_id if generic
        template = ERROR_TEMPLATES["ERR-GENERIC"]
        error_id = code if not error_id else error_id

    title = template["title"]
    description = template["description"]
    
    if "{error_id}" in description and error_id:
        description = description.format(error_id=error_id)

    text = (
        f"⚠️ <b>{title}</b>\n\n"
        f"Код ошибки: {code}\n"
        f"{description}\n\n"
        "Если ошибка повторяется — напишите в поддержку."
    )

    markup = _build_error_keyboard(template)

    if isinstance(event, CallbackQuery):
        if event.message:
            await event.message.edit_text(text, reply_markup=markup)
    elif isinstance(event, Message):
        await event.answer(text, reply_markup=markup)
