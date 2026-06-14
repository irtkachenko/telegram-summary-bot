"""
queries.py — запити до БД для Celery воркера.

Містить функції для отримання повідомлень та назви чату.
Підключається до PostgreSQL напряму (не через пул, бо це окремий процес).
"""
import logging
import os
from datetime import datetime, timedelta

import asyncpg

logger = logging.getLogger(__name__)


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
        raise

    try:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM messages WHERE chat_id = $1",
            chat_id,
        )
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

        messages = [
            {"user_name": row["user_name"], "text": row["text"]}
            for row in rows
        ]
        logger.info(
            f"📥 Отримано {len(messages)} повідомлень "
            f"для чату {chat_id} за період {period}"
        )
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
