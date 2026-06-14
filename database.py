"""
database.py — підключення до PostgreSQL та створення таблиць.

Використовує asyncpg для асинхронної роботи з БД.
Функція init_db() створює таблиці, якщо їх ще немає.
"""

import os
import asyncpg
import logging

logger = logging.getLogger(__name__)


async def get_pool() -> asyncpg.Pool:
    """
    Створює та повертає пул з'єднань до PostgreSQL.
    Параметри підключення беруться зі змінних оточення.
    """
    return await asyncpg.create_pool(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "tg_user"),
        password=os.getenv("DB_PASSWORD", "strong_password_here"),
        database=os.getenv("DB_NAME", "tg_summarizer"),
        min_size=2,
        max_size=10,
    )


async def init_db(pool: asyncpg.Pool) -> None:
    """
    Створює таблиці chats та messages, якщо вони ще не існують.

    Таблиця chats:
      - chat_id (BIGINT, PRIMARY KEY) — ID чату в Telegram
      - chat_title (TEXT) — назва чату
      - updated_at (TIMESTAMP) — час останнього оновлення

    Таблиця messages:
      - id (SERIAL, PRIMARY KEY)
      - chat_id (BIGINT, FOREIGN KEY -> chats.chat_id)
      - user_id (BIGINT) — ID користувача в Telegram
      - user_name (TEXT) — ім'я або нікнейм користувача
      - text (TEXT) — текст повідомлення
      - created_at (TIMESTAMP) — час повідомлення
    """
    async with pool.acquire() as conn:
        # Створюємо таблицю chats
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id BIGINT PRIMARY KEY,
                chat_title TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)

        # Створюємо таблицю messages
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                user_name TEXT NOT NULL DEFAULT 'Unknown',
                text TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        # Індекс для швидкого пошуку повідомлень по чату та часу
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_created
            ON messages (chat_id, created_at);
        """)

        logger.info("Database tables initialized successfully.")