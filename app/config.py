"""
config.py — централізована конфігурація проєкту.

Читає змінні оточення з .env, валідує їх,
налаштовує логування.
"""

import logging
import os
import sys

from dotenv import load_dotenv

# Завантажуємо .env
load_dotenv()

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Змінні з .env
BOT_TOKEN_RAW = os.getenv("BOT_TOKEN", "")
BOT_OWNER_ID_RAW = os.getenv("BOT_OWNER_ID", "0")

# Валідація BOT_TOKEN
if not BOT_TOKEN_RAW or BOT_TOKEN_RAW == "your_telegram_bot_token_here":
    logger.critical("❌ BOT_TOKEN не задано або використовується шаблонне значення!")
    sys.exit(1)
bot_token = BOT_TOKEN_RAW

# Валідація BOT_OWNER_ID
try:
    bot_owner_id = int(BOT_OWNER_ID_RAW)
except (ValueError, TypeError):
    bot_owner_id = 0

if bot_owner_id == 0:
    logger.critical("❌ BOT_OWNER_ID не задано, порожнє або дорівнює 0!")
    sys.exit(1)

logger.info("✅ Конфігурація завантажена успішно")
