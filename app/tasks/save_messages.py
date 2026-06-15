"""
save_messages.py — періодична Celery задача для збереження повідомлень.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import asyncpg

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.services.redis import MESSAGE_QUEUE_PREFIX, create_standalone_client
from app.tasks.app import celery_app

logger = logging.getLogger(__name__)
BATCH_SIZE = 100


async def _get_all_queue_keys(client) -> list[str]:
    """Повертає список усіх ключів черги повідомлень."""
    cursor, keys = 0, []
    while True:
        cursor, batch = await client.scan(
            cursor=cursor, match=f"{MESSAGE_QUEUE_PREFIX}*", count=100
        )
        keys.extend(batch)
        if cursor == 0:
            break
    return keys


async def _pop_all_messages(client, key: str) -> list[dict]:
    """Атомарно отримує всі повідомлення з черги та очищає її."""
    pipe = client.pipeline(transaction=True)
    pipe.lrange(key, 0, -1)
    pipe.delete(key)
    results, _ = await pipe.execute()

    if not results:
        return []

    messages = []
    for raw in results:
        try:
            messages.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"❌ Помилка декодування JSON з Redis: {e}")

    logger.info(f"📤 Витягнуто {len(messages)} повідомлень з {key}")
    return messages


async def _save_chats(conn, messages: list[dict], now: datetime):
    """UPSERT унікальних чатів у базу даних."""
    chats = {
        msg["chat_id"]: msg.get("chat_title") or f"Chat #{msg['chat_id']}"
        for msg in messages
    }
    
    for chat_id, chat_title in chats.items():
        await conn.execute(
            """
            INSERT INTO chats (chat_id, chat_title, updated_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (chat_id)
            DO UPDATE SET chat_title = $2, updated_at = $3
            """,
            chat_id, chat_title, now
        )


async def _save_messages_batch(conn, messages: list[dict]):
    """Пакетна вставка повідомлень через executemany."""
    for i in range(0, len(messages), BATCH_SIZE):
        batch = messages[i : i + BATCH_SIZE]
        args_list = []

        for msg in batch:
            try:
                args_list.append((
                    msg["chat_id"],
                    msg["user_id"],
                    msg["user_name"],
                    msg["text"],
                    datetime.fromisoformat(msg["created_at"])
                ))
            except Exception as e:
                logger.error(f"❌ Помилка підготовки повідомлення: {e}")

        if args_list:
            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO messages (chat_id, user_id, user_name, text, created_at)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    args_list
                )
        logger.info(f"✅ Записано batch {i + 1}–{i + len(batch)} з {len(messages)}")


async def async_flush_messages():
    """Основна асинхронна бізнес-логіка переносу даних."""
    # 1. Спочатку БД — якщо Postgres лежить, Redis не чіпаємо
    try:
        conn = await asyncpg.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
    except Exception as e:
        logger.error(f"❌ БД недоступна, скасовуємо флаш. Повідомлення в безпеці в Redis: {e}")
        return

    client = await create_standalone_client()
    try:
        # 2. Збір ключів
        keys = await _get_all_queue_keys(client)
        if not keys:
            logger.debug("⏳ Черга повідомлень порожня, пропускаємо")
            return

        # 3. Збір повідомлень
        all_messages = []
        for key in keys:
            all_messages.extend(await _pop_all_messages(client, key))

        if not all_messages:
            logger.info("⏳ Повідомлень у чергах не знайдено")
            return

        # 4. Запис у PostgreSQL
        logger.info(f"📦 Початок запису {len(all_messages)} повідомлень у БД...")
        await _save_chats(conn, all_messages, datetime.now(timezone.utc))
        await _save_messages_batch(conn, all_messages)
        logger.info(f"✅ Успішно синхронізовано {len(all_messages)} повідомлень")

    except Exception as e:
        logger.error(f"❌ Критична помилка під час обробки задач: {e}")
    finally:
        await asyncio.gather(conn.close(), client.aclose(), return_exceptions=True)


@celery_app.task(
    name="save_messages_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def save_messages_task(self):
    """Синхронна обгортка Celery для запуску асинхронного флашу."""
    logger.info("🔄 save_messages_task: запуск синхронізації")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(async_flush_messages())
        return 0
    except Exception as e:
        logger.error(f"❌ Помилка в save_messages_task: {e}")
        self.retry(exc=e)
        return -1
    finally:
        loop.close()