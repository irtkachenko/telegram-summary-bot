"""
errors.py — глобальний обробник помилок Telegram бота.

Ловить всі необроблені винятки та повідомляє власника.
"""
import logging

from aiogram import types

from app import bot_instance
from app.config import bot_owner_id

logger = logging.getLogger(__name__)


@bot_instance.dp.errors()
async def errors_handler(event: types.ErrorEvent):
    """
    Глобальний обробник помилок.
    Ловить всі необроблені винятки.
    """
    exception = event.exception

    logger.error(
        f"❌ Глобальна помилка: {exception}",
        exc_info=True,
    )

    # Спроба повідомити власника про критичну помилку
    try:
        error_text = f"⚠️ *Критична помилка бота*\n\n`{str(exception)[:200]}`"
        await bot_instance.bot.send_message(
            chat_id=bot_owner_id,
            text=error_text,
            parse_mode="Markdown",
        )
    except Exception:
        pass
