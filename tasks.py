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
import re
from datetime import datetime, timedelta

from dotenv import load_dotenv
from celery import Celery
from openai import AsyncOpenAI
from aiogram import Bot
from aiogram.enums import ParseMode
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


def escape_markdown(text: str) -> str:
    """
    Екранує спеціальні символи MarkdownV2.
    Telegram використовує MarkdownV2, де потрібно екранувати:
    _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", text)


async def fetch_messages(chat_id: int, period: str) -> list[dict]:
    """
    Отримує повідомлення з PostgreSQL для заданого чату та періоду.
    """
    since = datetime.utcnow() - get_period_timedelta(period)

    try:
        conn = await asyncpg.connect(
            host=os.getenv("DB_HOST", "postgres"),
            port=int(os.getenv("DB_PORT", 5432)),
            user=os.getenv("DB_USER", "tg_user"),
            password=os.getenv("DB_PASSWORD", "strong_password_here"),
            database=os.getenv("DB_NAME", "tg_summarizer"),
        )
    except Exception as e:
        logger.error(f"❌ Помилка підключення до БД (fetch_messages): {e}")
        raise  # Прокидаємо далі для retry

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

    except Exception as e:
        logger.error(f"❌ Помилка запиту до БД (fetch_messages): {e}")
        raise
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def get_chat_title(chat_id: int) -> str:
    """
    Отримує назву чату з БД по його ID.
    """
    try:
        conn = await asyncpg.connect(
            host=os.getenv("DB_HOST", "postgres"),
            port=int(os.getenv("DB_PORT", 5432)),
            user=os.getenv("DB_USER", "tg_user"),
            password=os.getenv("DB_PASSWORD", "strong_password_here"),
            database=os.getenv("DB_NAME", "tg_summarizer"),
        )
    except Exception as e:
        logger.error(f"❌ Помилка підключення до БД (get_chat_title): {e}")
        return f"Chat #{chat_id}"

    try:
        row = await conn.fetchrow(
            "SELECT chat_title FROM chats WHERE chat_id = $1",
            chat_id,
        )
        return row["chat_title"] if row else f"Chat #{chat_id}"
    except Exception as e:
        logger.error(f"❌ Помилка запиту до БД (get_chat_title): {e}")
        return f"Chat #{chat_id}"
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def generate_summary_with_openai(messages_text: str) -> tuple:
    """
    Надсилає текст повідомлень в OpenAI-сумісне API (Groq, OpenAI тощо)
    та отримує підсумок українською мовою.

    Модель та базовий URL беруться зі змінних оточення:
    - OPENAI_API_KEY — API ключ
    - OPENAI_API_BASE_URL — базовий URL (для Groq: https://api.groq.com/openai/v1)
    - MODEL_NAME — назва моделі (напр. llama-3.3-70b-versatile, gpt-4o-mini)
    
    Повертає (summary: str | None, error: str | None)
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        return None, "❌ Не задано OPENAI_API_KEY в .env файлі."

    base_url = os.getenv("OPENAI_API_BASE_URL")
    model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")

    # Валідація: перевіряємо, чи хоч якийсь URL задано
    if not base_url:
        logger.warning("⚠️ OPENAI_API_BASE_URL не задано, використовується стандартний OpenAI API")

    # Створюємо клієнт: якщо є base_url — використовуємо його (Groq),
    # інакше — стандартний OpenAI API
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    try:
        client = AsyncOpenAI(**client_kwargs)
    except Exception as e:
        logger.error(f"❌ Помилка створення OpenAI клієнта: {e}")
        return None, f"❌ Помилка ініціалізації AI клієнта: {str(e)}"

    system_prompt = (
        "Ти — асистент, який аналізує чати в Telegram та створює структуровані підсумки. "
        "Твоя задача — проаналізувати надані повідомлення з групового чату та створити "
        "короткий, змістовний підсумок українською мовою.\n\n"
        "Формат відповіді:\n"
        "📊 Підсумок чату\n\n"
        "Основні теми обговорення:\n"
        "- Тема 1\n"
        "- Тема 2\n\n"
        "Ключові висновки:\n"
        "- Висновок 1\n"
        "- Висновок 2\n\n"
        "Активні учасники:\n"
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
        if not summary:
            logger.warning("⚠️ API повернуло порожній підсумок")
            return None, "❌ API повернуло порожній підсумок."

        logger.info("🤖 Підсумок успішно згенеровано")
        return summary, None

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Помилка API: {error_msg}")
        return None, f"❌ Помилка при генерації підсумку: {error_msg}"


async def send_summary_to_user(bot_token: str, user_id: int, summary: str, chat_title: str) -> str | None:
    """
    Надсилає згенерований підсумок користувачу через Telegram бота.
    Використовує MarkdownV2 з екрануванням спеціальних символів.
    Повертає None при успіху, або текст помилки.
    """
    bot = Bot(token=bot_token)
    try:
        # Екрануємо текст для MarkdownV2
        safe_title = escape_markdown(chat_title)
        safe_summary = escape_markdown(summary)

        await bot.send_message(
            chat_id=user_id,
            text=f"📋 *Підсумок чату: {safe_title}*\n\n{safe_summary}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        logger.info(f"✅ Підсумок надіслано користувачу {user_id}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Не вдалося надіслати з MarkdownV2: {e}")
        # Якщо MarkdownV2 не спрацював — пробуємо без форматування
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"📋 Підсумок чату: {chat_title}\n\n{summary}",
            )
            logger.info(f"✅ Підсумок надіслано (без форматування) користувачу {user_id}")
            return None
        except Exception as e2:
            error_msg = str(e2)
            logger.error(f"❌ Помилка при надсиланні повідомлення: {error_msg}")
            return error_msg
    finally:
        try:
            await bot.close()
        except Exception:
            # Ігноруємо помилки закриття бота (flood control тощо)
            pass


async def send_error_to_user(bot_token: str, user_id: int, error_message: str, chat_title: str = ""):
    """
    Надсилає повідомлення про помилку користувачу.
    """
    bot = Bot(token=bot_token)
    try:
        text = f"❌ *Помилка*"
        if chat_title:
            text += f" при обробці чату {escape_markdown(chat_title)}"
        text += f":\n\n{escape_markdown(error_message)}"

        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        logger.info(f"✅ Повідомлення про помилку надіслано користувачу {user_id}")
    except Exception:
        # Якщо Markdown не спрацював — надсилаємо звичайний текст
        try:
            text = f"❌ Помилка: {error_message}"
            if chat_title:
                text = f"❌ Помилка при обробці чату {chat_title}: {error_message}"
            await bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            logger.error(f"❌ Критична помилка: не вдалося надіслати повідомлення про помилку: {e}")
    finally:
        try:
            await bot.close()
        except Exception:
            pass


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
    loop = None
    bot_token = os.getenv("BOT_TOKEN")

    if not bot_token:
        logger.error("❌ BOT_TOKEN не знайдено в оточенні")
        return

    # Стек помилок для логування
    errors = []

    try:
        # Створюємо event loop для асинхронних операцій
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 1. Отримуємо повідомлення з БД
        messages = loop.run_until_complete(fetch_messages(chat_id, period))

        if not messages:
            # Немає повідомлень — надсилаємо відповідне повідомлення
            chat_title = loop.run_until_complete(get_chat_title(chat_id))
            summary = "📭 За вибраний період немає повідомлень для аналізу."
            error = loop.run_until_complete(
                send_summary_to_user(bot_token, user_id, summary, chat_title)
            )
            if error:
                logger.error(f"❌ Не вдалося надіслати підсумок: {error}")
                errors.append(error)
            logger.info(f"✅ Підсумок для чату {chat_id} надіслано (немає повідомлень)")
            return

        # 2. Форматуємо повідомлення в текст
        formatted_text = "\n\n".join(
            f"👤 {msg['user_name']}: {msg['text']}"
            for msg in messages
        )

        # Обмежуємо розмір тексту (10000 символів через обмеження API)
        formatted_text = formatted_text[:10000]

        # 3. Генеруємо підсумок через API
        summary, api_error = loop.run_until_complete(
            generate_summary_with_openai(formatted_text)
        )

        # 4. Отримуємо назву чату
        chat_title = loop.run_until_complete(get_chat_title(chat_id))

        if api_error:
            # Помилка API — надсилаємо користувачу повідомлення про помилку
            logger.error(f"❌ Помилка API для чату {chat_id}: {api_error}")
            errors.append(api_error)
            loop.run_until_complete(
                send_error_to_user(bot_token, user_id, api_error, chat_title)
            )
        else:
            # 5. Надсилаємо підсумок власнику
            error = loop.run_until_complete(
                send_summary_to_user(bot_token, user_id, summary, chat_title)
            )
            if error:
                logger.error(f"❌ Не вдалося надіслати підсумок: {error}")
                errors.append(error)

        logger.info(f"✅ Задача generate_summary_task завершена для чату {chat_id}")

    except asyncio.CancelledError:
        logger.warning(f"⚠️ Задача для чату {chat_id} скасована")
        return

    except MemoryError:
        logger.error(f"❌ Недостатньо пам'яті для обробки чату {chat_id}")
        try:
            if loop is not None and bot_token:
                loop.run_until_complete(
                    send_error_to_user(bot_token, user_id, "❌ Недостатньо пам'яті для обробки. Спробуйте коротший період.")
                )
        except Exception:
            pass
        # Не retry при MemoryError — це не допоможе

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Критична помилка в generate_summary_task: {error_msg}")
        errors.append(error_msg)

        # Спроба повідомити користувача про помилку
        if bot_token:
            try:
                # Створюємо НОВИЙ event loop, бо старий може бути закритий
                error_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(error_loop)
                try:
                    error_loop.run_until_complete(
                        send_error_to_user(bot_token, user_id, error_msg)
                    )
                finally:
                    try:
                        error_loop.close()
                    except Exception:
                        pass
            except Exception:
                logger.error("❌ Не вдалося надіслати повідомлення про помилку")

        # Спроба повторити задачу
        try:
            self.retry(exc=e)
        except Exception as retry_error:
            logger.error(f"❌ Не вдалося повторити задачу: {retry_error}")

    finally:
        # Безпечне закриття event loop
        if loop is not None:
            try:
                # Скасовуємо всі незавершені задачі (тільки якщо loop не закритий)
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except (RuntimeError, asyncio.CancelledError):
                    # Loop already closed or tasks already done
                    pass
            except Exception:
                pass
            finally:
                try:
                    # Перевіряємо, чи loop ще не закритий
                    if not loop.is_closed():
                        loop.close()
                except (RuntimeError, Exception):
                    pass