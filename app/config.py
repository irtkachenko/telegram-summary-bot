import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Зчитування змінних
BOT_TOKEN_RAW = os.getenv("BOT_TOKEN", "")
BOT_OWNER_ID_RAW = os.getenv("BOT_OWNER_ID", "0")
OPENAI_API_KEY_RAW = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE_URL_RAW = os.getenv("OPENAI_API_BASE_URL", "").strip()
MODEL_NAME_RAW = os.getenv("MODEL_NAME", "").strip()

# Database
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "tg_summarizer")
DB_USER = os.getenv("DB_USER", "tg_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "strong_password_here")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Валідація Telegram Bot
if not BOT_TOKEN_RAW:
    logger.critical("❌ BOT_TOKEN не задано у файлі .env!")
    sys.exit(1)
bot_token = BOT_TOKEN_RAW

try:
    bot_owner_id = int(BOT_OWNER_ID_RAW)
except (ValueError, TypeError):
    bot_owner_id = 0

if bot_owner_id == 0:
    logger.critical("❌ BOT_OWNER_ID не задано або має неправильний формат!")
    sys.exit(1)

# Валідація Groq (OpenAI SDK)
if not OPENAI_API_KEY_RAW:
    logger.critical("❌ API ключ (OPENAI_API_KEY) не задано у файлі .env!")
    sys.exit(1)
openai_api_key = OPENAI_API_KEY_RAW

if not OPENAI_API_BASE_URL_RAW:
    logger.critical("❌ OPENAI_API_BASE_URL не задано! Для Groq цей параметр обов'язковий.")
    sys.exit(1)
openai_api_base_url = OPENAI_API_BASE_URL_RAW

model_name = MODEL_NAME_RAW or "llama3-8b-8192"

logger.info(f"🤖 Модель ШІ: {model_name}")
logger.info("✅ Конфігурація завантажена успішно")