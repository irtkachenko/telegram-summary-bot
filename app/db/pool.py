"""
pool.py — створення пулу з'єднань до PostgreSQL.

Використовує asyncpg.
Параметри підключення беруться з централізованої конфігурації.
"""

import asyncpg

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


async def get_db_pool() -> asyncpg.Pool:
    """
    Створює та повертає пул з'єднань до PostgreSQL.
    """
    return await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        min_size=2,
        max_size=10,
    )