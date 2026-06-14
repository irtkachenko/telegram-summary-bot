"""
owner.py — фільтр IsBotOwner.

Пропускає тільки повідомлення від власника бота.
"""
from aiogram import types
from aiogram.filters import BaseFilter
from app.config import bot_owner_id


class IsBotOwner(BaseFilter):
    """Пропускає тільки повідомлення від BOT_OWNER_ID."""

    async def __call__(self, message: types.Message) -> bool:
        try:
            return message.from_user.id == bot_owner_id
        except AttributeError:
            return False