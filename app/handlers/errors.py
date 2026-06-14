"""
errors.py — глобальний обробник помилок Telegram бота.
"""
import logging

from aiogram import Router, types

from app.config import bot_owner_id

logger = logging.getLogger(__name__)

router = Router()


@router.errors()
async def errors_handler(event: types.ErrorEvent):
    """
    Глобальний обробник помилок.
    """
    exception = event.exception

    logger.error(
        f"❌ Глобальна помилка: {exception}",
        exc_info=True,
    )

    # Спроба повідомити власника про критичну помилку
    try:
        from app.main import bot

        error_text = f"⚠️ *Критична помилка бота*\n\n`{str(exception)[:200]}`"
        await bot.send_message(
            chat_id=bot_owner_id,
            text=error_text,
            parse_mode="Markdown",
        )
    except Exception:
        pass