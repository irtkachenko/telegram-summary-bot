"""
callbacks.py — Callback Data фабрики та функції для створення клавіатур.

Використовує aiogram 3.x InlineKeyboardBuilder та CallbackData.
"""

from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder


class ChatSelect(CallbackData, prefix="chat"):
    """
    Callback для вибору чату.
    chat_id — ID вибраного чату.
    """
    chat_id: int


class PeriodSelect(CallbackData, prefix="period"):
    """
    Callback для вибору періоду.
    chat_id — ID чату, для якого генеруємо підсумок.
    period — рядок: "1d", "3d" або "7d".
    """
    chat_id: int
    period: str


def chat_list_keyboard(rows: list[dict]) -> InlineKeyboardBuilder:
    """
    Створює інлайн-клавіатуру зі списком чатів.

    rows — список словників з ключами chat_id та chat_title.
    """
    builder = InlineKeyboardBuilder()
    for row in rows:
        chat_id = row["chat_id"]
        title = row["chat_title"]
        builder.button(
            text=title,
            callback_data=ChatSelect(chat_id=chat_id).pack()
        )
    builder.adjust(1)
    return builder


def period_keyboard(chat_id: int) -> InlineKeyboardBuilder:
    """
    Створює інлайн-клавіатуру з вибором періоду (1d, 3d, 7d).

    chat_id — ID чату, для якого вибираємо період.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="1 Day",
        callback_data=PeriodSelect(chat_id=chat_id, period="1d").pack()
    )
    builder.button(
        text="3 Days",
        callback_data=PeriodSelect(chat_id=chat_id, period="3d").pack()
    )
    builder.button(
        text="1 Week",
        callback_data=PeriodSelect(chat_id=chat_id, period="7d").pack()
    )
    builder.adjust(1)
    return builder
