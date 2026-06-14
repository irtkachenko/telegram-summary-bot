"""
pool.py — створення пулу з'єднань до PostgreSQL.

Використовує asyncpg.
Параметри підключення беруться зі змінних оточення.
"""
import os

import asyncpg


async def get_db_pool() -> asyncpg.Pool:
    """
    Створює та повертає пул з'єднань до PostgreSQL.
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
