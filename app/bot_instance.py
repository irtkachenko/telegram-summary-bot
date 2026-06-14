"""
bot_instance.py — створення глобальних екземплярів Bot та Dispatcher.

db_pool заповнюється при старті в main().
Оскільки це модуль, handlers звертаються через bot_instance.db_pool,
а не через імпорт значення — це дозволяє побачити оновлене значення після запуску.
"""
import sys

from aiogram import Bot, Dispatcher

from app.config import bot_token, logger

# Створюємо екземпляри
try:
    bot = Bot(token=bot_token)
    logger.info("✅ Бот створено успішно")
except Exception as e:
    logger.critical(f"❌ Помилка створення бота: {e}")
    sys.exit(1)

dp = Dispatcher()

# Глобальний пул з'єднань до БД (заповниться при старті в main())
db_pool = None
