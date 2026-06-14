"""
bot.py — вхідна точка для запуску Telegram бота.

Просто делегує в app.__main__.
"""
from app.__main__ import main

if __name__ == "__main__":
    import asyncio
    import sys

    from app.config import logger

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот зупинено користувачем")
    except Exception as e:
        logger.critical(f"❌ Фатальна помилка: {e}", exc_info=True)
        sys.exit(1)
