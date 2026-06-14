"""
Entry point for `python -m app`.
Runs the bot.
"""
import asyncio
import sys

from app.config import logger
from app import bot_instance
from app.db.pool import get_db_pool
from app.db.models import init_db

import app.handlers  # noqa: F401 — register handlers


async def main():
    """Initialize DB and start polling."""
    logger.info("🚀 Запуск бота...")

    try:
        bot_instance.db_pool = await get_db_pool()
        logger.info("✅ Пул з'єднань до БД створено")

        await init_db(bot_instance.db_pool)
        logger.info("✅ Таблиці БД ініціалізовано")
    except Exception as e:
        logger.critical(f"❌ Критична помилка при ініціалізації БД: {e}")
        sys.exit(1)

    logger.info("✅ База даних готова. Бот запускається...")

    from aiogram.exceptions import (
        TelegramUnauthorizedError,
        TelegramConflictError,
    )

    try:
        logger.info("🤖 Бот запущений та слухає...")
        await bot_instance.dp.start_polling(bot_instance.bot)
    except TelegramUnauthorizedError:
        logger.critical("❌ Недійсний BOT_TOKEN! Перевірте .env файл.")
        sys.exit(1)
    except TelegramConflictError:
        logger.critical(
            "❌ Конфлікт: інший екземпляр бота вже запущений. "
            "Зупиніть його та спробуйте знову."
        )
        sys.exit(1)
    except Exception as e:
        logger.critical(f"❌ Критична помилка при запуску бота: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот зупинено користувачем")
    except Exception as e:
        logger.critical(f"❌ Фатальна помилка: {e}", exc_info=True)
        sys.exit(1)