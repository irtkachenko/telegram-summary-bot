"""
owner.py — функція-фільтр для перевірки власника бота.

Пропускає тільки повідомлення від BOT_OWNER_ID.
"""
from aiogram import types

from app.config import bot_owner_id


async def is_bot_owner(message: types.Message) -> bool:
    """Перевіряє, чи є відправник повідомлення власником бота."""
    try:
        return message.from_user.id == bot_owner_id
    except AttributeError:
        return False