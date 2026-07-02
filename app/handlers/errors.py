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
        import html
        bot = event.bot
        safe_error = html.escape(str(exception)[:200], quote=True)
        error_text = f"⚠️ <b>Критична помилка бота</b>\n\n<code>{safe_error}</code>"
        await bot.send_message(
            chat_id=bot_owner_id,
            text=error_text,
            parse_mode="HTML",
        )
    except Exception:
        pass