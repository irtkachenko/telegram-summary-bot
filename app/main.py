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
from app.services.redis import close_redis, init_redis

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

    # 2. Redis клієнт (для буферизації повідомлень)
    try:
        await init_redis()
        logger.info("✅ Пряме з'єднання з Redis встановлено")
    except Exception as e:
        logger.critical(f"❌ Критична помилка при ініціалізації Redis: {e}")
        sys.exit(1)

    # 3. Dispatcher
    dp = Dispatcher()

    # 4. Пул БД
    try:
        db_pool = await get_db_pool()
        logger.info("✅ Пул з'єднань до БД створено")
        await init_db(db_pool)
        logger.info("✅ Таблиці БД ініціалізовано")
    except Exception as e:
        logger.critical(f"❌ Критична помилка при ініціалізації БД: {e}")
        sys.exit(1)

    # 5. Middleware — передає db_pool у кожен обробник через data
    @dp.update.outer_middleware
    async def db_pool_middleware(handler, event: types.Update, data: dict):
        data["db_pool"] = db_pool
        return await handler(event, data)

    # 6. Реєструємо роутери
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
    finally:
        # Закриваємо Redis при зупинці (у тому ж event loop)
        try:
            await close_redis()
            logger.info("🔌 Redis клієнт закрито")
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот зупинено користувачем")
    except Exception as e:
        logger.critical(f"❌ Фатальна помилка: {e}", exc_info=True)
        sys.exit(1)
