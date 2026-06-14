"""
tasks.py — Celery-воркер для генерації підсумків чатів.

Запускається окремо від бота.
Отримує завдання з Redis, підключається до PostgreSQL,
збирає повідомлення, надсилає їх в OpenAI-сумісне API (Groq, OpenAI тощо)
та відправляє результат власнику бота через Telegram.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
from celery import Celery
from openai import AsyncOpenAI
from aiogram import Bot
import asyncpg

# Завантажуємо змінні оточення
load_dotenv()

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Створюємо Celery додаток
# Брокер та бекенд — Redis
celery_app = Celery(
    "tg_summarizer",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
)

# Налаштування Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


def get_period_timedelta(period: str) -> timedelta:
    """
    Перетворює рядок періоду ("1d", "3d", "7d") в об'єкт timedelta.
    """
    if period == "1d":
        return timedelta(days=1)
    elif period == "3d":
        return timedelta(days=3)
    elif period == "7d":
        return timedelta(weeks=1)
    else:
        return timedelta(days=1)


async def fetch_messages(chat_id: int, period: str) -> list[dict]:
    """
    Отримує повідомлення з PostgreSQL для заданого чату та періоду.
    """
    since = datetime.utcnow() - get_period_timedelta(period)

    conn = await asyncpg.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "tg_user"),
        password=os.getenv("DB_PASSWORD", "strong_password_here"),
        database=os.getenv("DB_NAME", "tg_summarizer"),
    )

    try:
        # Дебаг: перевіряємо, скільки всього повідомлень для цього чату
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM messages WHERE chat_id = $1",
            chat_id,
        )
        # Перевіряємо діапазон дат
        date_range = await conn.fetchrow(
            """
            SELECT MIN(created_at) as min_date, MAX(created_at) as max_date
            FROM messages WHERE chat_id = $1
            """,
            chat_id,
        )
        logger.info(
            f"🔍 Дебаг: chat_id={chat_id}, "
            f"всього повідомлень={total}, "
            f"since={since}, "
            f"min_date={date_range['min_date']}, "
            f"max_date={date_range['max_date']}"
        )

        rows = await conn.fetch(
            """
            SELECT user_name, text
            FROM messages
            WHERE chat_id = $1 AND created_at >= $2
            ORDER BY created_at ASC
            """,
            chat_id,
            since,
        )

        messages = [{"user_name": row["user_name"], "text": row["text"]} for row in rows]
        logger.info(f"📥 Отримано {len(messages)} повідомлень для чату {chat_id} за період {period}")
        return messages

    finally:
        await conn.close()


async def get_chat_title(chat_id: int) -> str:
    """
    Отримує назву чату з БД по його ID.
    """
    conn = await asyncpg.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "tg_user"),
        password=os.getenv("DB_PASSWORD", "strong_password_here"),
        database=os.getenv("DB_NAME", "tg_summarizer"),
    )
    try:
        row = await conn.fetchrow(
            "SELECT chat_title FROM chats WHERE chat_id = $1",
            chat_id,
        )
        return row["chat_title"] if row else f"Chat #{chat_id}"
    finally:
        await conn.close()


async def generate_summary_with_openai(messages_text: str) -> str:
    """
    Надсилає текст повідомлень в OpenAI-сумісне API (Groq, OpenAI тощо)
    та отримує підсумок українською мовою.

    Модель та базовий URL беруться зі змінних оточення:
    - OPENAI_API_KEY — API ключ
    - OPENAI_API_BASE_URL — базовий URL (для Groq: https://api.groq.com/openai/v1)
    - MODEL_NAME — назва моделі (напр. llama3-70b-8192, gpt-4o-mini)
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        return "❌ Не задано OPENAI_API_KEY в .env файлі."

    base_url = os.getenv("OPENAI_API_BASE_URL")
    model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")

    # Створюємо клієнт: якщо є base_url — використовуємо його (Groq),
    # інакше — стандартний OpenAI API
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = AsyncOpenAI(**client_kwargs)

    system_prompt = (
        "Ти — асистент, який аналізує чати в Telegram та створює структуровані підсумки. "
        "Твоя задача — проаналізувати надані повідомлення з групового чату та створити "
        "короткий, змістовний підсумок українською мовою.\n\n"
        "Формат відповіді:\n"
        "📊 **Підсумок чату**\n\n"
        "**Основні теми обговорення:**\n"
        "- Тема 1\n"
        "- Тема 2\n\n"
        "**Ключові висновки:**\n"
        "- Висновок 1\n"
        "- Висновок 2\n\n"
        "**Активні учасники:**\n"
        "- @username1\n"
        "- @username2\n\n"
        "Будь лаконічним та інформативним. Використовуй емодзі для кращої читабельності."
    )

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Ось повідомлення з чату для аналізу:\n\n{messages_text}"},
            ],
            max_tokens=1500,
            temperature=0.7,
        )

        summary = response.choices[0].message.content
        logger.info("🤖 Підсумок успішно згенеровано")
        return summary

    except Exception as e:
        logger.error(f"❌ Помилка API: {e}")
        return f"❌ Помилка при генерації підсумку: {str(e)}"


async def send_summary_to_user(bot_token: str, user_id: int, summary: str, chat_title: str):
    """
    Надсилає згенерований підсумок користувачу через Telegram бота.
    """
    bot = Bot(token=bot_token)
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"📋 **Підсумок чату: {chat_title}**\n\n{summary}",
            parse_mode="Markdown",
        )
        logger.info(f"✅ Підсумок надіслано користувачу {user_id}")
    except Exception as e:
        logger.error(f"❌ Помилка при надсиланні повідомлення: {e}")
    finally:
        await bot.close()


# ===== Celery задача =====
@celery_app.task(
    name="generate_summary_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def generate_summary_task(self, chat_id: int, period: str, user_id: int):
    """
    Celery задача для генерації підсумку чату.

    1. Підключається до PostgreSQL та отримує повідомлення.
    2. Форматує їх в текст.
    3. Надсилає в OpenAI-сумісне API.
    4. Відправляє результат власнику бота.
    """
    try:
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            logger.error("❌ BOT_TOKEN не знайдено в оточенні")
            return

        # Створюємо event loop для асинхронних операцій
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 1. Отримуємо повідомлення з БД
        messages = loop.run_until_complete(fetch_messages(chat_id, period))

        if not messages:
            # Немає повідомлень — надсилаємо відповідне повідомлення
            chat_title = loop.run_until_complete(get_chat_title(chat_id))
            summary = "📭 За вибраний період немає повідомлень для аналізу."
            loop.run_until_complete(
                send_summary_to_user(bot_token, user_id, summary, chat_title)
            )
            logger.info(f"✅ Підсумок для чату {chat_id} надіслано (немає повідомлень)")
            loop.close()
            return

        # 2. Форматуємо повідомлення в текст
        formatted_text = "\n\n".join(
            f"👤 {msg['user_name']}: {msg['text']}"
            for msg in messages
        )

        # Обмежуємо розмір тексту (10000 символів через обмеження API)
        formatted_text = formatted_text[:10000]

        # 3. Генеруємо підсумок через API
        summary = loop.run_until_complete(
            generate_summary_with_openai(formatted_text)
        )

        # 4. Отримуємо назву чату
        chat_title = loop.run_until_complete(get_chat_title(chat_id))

        # 5. Надсилаємо підсумок власнику
        loop.run_until_complete(
            send_summary_to_user(bot_token, user_id, summary, chat_title)
        )

        loop.close()
        logger.info(f"✅ Задача generate_summary_task завершена для чату {chat_id}")

    except Exception as e:
        logger.error(f"❌ Критична помилка в generate_summary_task: {e}")
        try:
            self.retry(exc=e)
        except Exception as retry_error:
            logger.error(f"❌ Не вдалося повторити задачу: {retry_error}")