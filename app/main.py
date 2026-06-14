"""
main.py — єдина точка входу в додаток.

Створює Bot, Dispatcher, пул БД, реєструє роутери й запускає polling.
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError

from app.config import bot_token, logger
from app.db.models import init_db
from app.db.pool import get_db_pool
from app.handlers import errors_router, group_router, summary_router

logger = logging.getLogger(__name__)

# Глобальні екземпляри (заповнюються в initialize())
bot: Bot | None = None
dp: Dispatcher | None = None
db_pool = None  # asyncpg.Pool


async def initialize():
    """Ініціалізує Bot, Dispatcher, пул БД та реєструє компоненти."""
    global bot, dp, db_pool

    # 1. Bot
    try:
        bot = Bot(token=bot_token)
        logger.info("✅ Бот створено успішно")
    except Exception as e:
        logger.critical(f"❌ Помилка створення бота: {e}")
        sys.exit(1)

    # 2. Dispatcher
    dp = Dispatcher()

    # 3. Пул БД
    try:
        db_pool = await get_db_pool()
        logger.info("✅ Пул з'єднань до БД створено")
        await init_db(db_pool)
        logger.info("✅ Таблиці БД ініціалізовано")
    except Exception as e:
        logger.critical(f"❌ Критична помилка при ініціалізації БД: {e}")
        sys.exit(1)

    # 4. Middleware — передає db_pool у кожен обробник через data
    @dp.update.outer_middleware
    async def db_pool_middleware(handler, event: types.Update, data: dict):
        data["db_pool"] = db_pool
        return await handler(event, data)

    # 5. Реєструємо роутери
    dp.include_router(errors_router)
    dp.include_router(group_router)
    dp.include_router(summary_router)

    logger.info("✅ Усі компоненти зареєстровано")


async def main():
    """Запускає бота (ініціалізація + polling)."""
    logger.info("🚀 Запуск бота...")

    await initialize()

    logger.info("✅ База даних готова. Бот запускається...")

    try:
        logger.info("🤖 Бот запущений та слухає...")
        await dp.start_polling(bot)
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