"""
save_messages.py — періодична Celery задача для збереження повідомлень.

Кожну хвилину (через Celery Beat):
  1. Отримує всі ключі черги повідомлень з Redis.
  2. Для кожного ключа atomically витягує всі повідомлення.
  3. Записує їх batch-ом в PostgreSQL:
     - upsert в таблицю chats
     - insert в таблицю messages

Використовує ізольований Redis-клієнт (create_standalone_client),
щоб уникнути проблем із закритим event loop при повторних запусках.
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

# Розмір batch-у для INSERT
BATCH_SIZE = 100


async def _get_all_queue_keys(client) -> list[str]:
    """Повертає список усіх ключів черги повідомлень, використовуючи переданий клієнт."""
    cursor = 0
    keys = []
    while True:
        cursor, batch = await client.scan(
            cursor=cursor,
            match=f"{MESSAGE_QUEUE_PREFIX}*",
            count=100,
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
            msg = json.loads(raw)
            messages.append(msg)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"❌ Помилка декодування JSON з Redis: {e}")

    logger.info(f"📤 Витягнуто {len(messages)} повідомлень з {key}")
    return messages


async def async_flush_messages():
    """
    Асинхронна логіка:
      1. Створює ізольований Redis-клієнт (не залежить від глобального).
      2. Отримує всі ключі черги (messages:queue:*).
      3. Для кожного ключа atomically дістає повідомлення.
      4. Розбиває на batch-и та записує в БД.
      5. Закриває Redis-клієнт.
    """
    # 0. Створюємо ізольований Redis-клієнт для цього запуску
    client = await create_standalone_client()
    try:
        # 1. Отримуємо всі ключі
        keys = await _get_all_queue_keys(client)
        if not keys:
            logger.debug("⏳ Черга повідомлень порожня, пропускаємо")
            return

        logger.info(f"🔄 Знайдено {len(keys)} черг для обробки")

        # 2. Для кожного ключа — atomically pop+delete
        all_messages: list[dict] = []

        for key in keys:
            messages = await _pop_all_messages(client, key)
            all_messages.extend(messages)

        if not all_messages:
            logger.info("⏳ Після pop — повідомлень немає (могли бути видалені)")
            return

        now = datetime.now(timezone.utc)
        logger.info(f"📦 Отримано {len(all_messages)} повідомлень з Redis")

        # 3. З'єднуємося з БД та batch-запис
        try:
            conn = await asyncpg.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
            )
        except Exception as e:
            logger.error(f"❌ Помилка підключення до БД: {e}")
            return

        try:
            # 3a. UPSERT чатів — збираємо унікальні chat_id з назвами
            chat_ids_with_title = {}
            for msg in all_messages:
                chat_id = msg["chat_id"]
                chat_title = msg.get("chat_title") or f"Chat #{chat_id}"
                chat_ids_with_title[chat_id] = chat_title

            for chat_id, chat_title in chat_ids_with_title.items():
                await conn.execute(
                    """
                    INSERT INTO chats (chat_id, chat_title, updated_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (chat_id)
                    DO UPDATE SET updated_at = $3
                    """,
                    chat_id,
                    chat_title,
                    now,
                )

            # 3b. Batch INSERT повідомлень
            for i in range(0, len(all_messages), BATCH_SIZE):
                batch = all_messages[i : i + BATCH_SIZE]

                async with conn.transaction():
                    for msg in batch:
                        try:
                            msg_date = datetime.fromisoformat(msg["created_at"])

                            await conn.execute(
                                """
                                INSERT INTO messages
                                    (chat_id, user_id, user_name, text, created_at)
                                VALUES ($1, $2, $3, $4, $5)
                                """,
                                msg["chat_id"],
                                msg["user_id"],
                                msg["user_name"],
                                msg["text"],
                                msg_date,
                            )
                        except Exception as e:
                            logger.error(f"❌ Помилка вставки повідомлення: {e}")

                logger.info(f"✅ Записано batch {i + 1}–{i + len(batch)} з {len(all_messages)}")

            logger.info(f"✅ Успішно збережено {len(all_messages)} повідомлень у PostgreSQL")

        except Exception as e:
            logger.error(f"❌ Помилка batch-запису в БД: {e}")
        finally:
            try:
                await conn.close()
            except Exception:
                pass

    finally:
        # 5. Закриваємо ізольований Redis-клієнт
        try:
            await client.aclose()
            logger.debug("🔌 Redis-клієнт закрито")
        except Exception:
            pass


@celery_app.task(
    name="save_messages_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def save_messages_task(self):
    """
    Celery задача, яка запускається кожну хвилину по розкладу.

    Виконує async_flush_messages всередині event loop.
    """
    logger.info("🔄 save_messages_task: початок синхронізації Redis → PostgreSQL")

    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(async_flush_messages())
        logger.info("✅ save_messages_task завершено успішно")
        return 0

    except asyncio.CancelledError:
        logger.warning("⚠️ save_messages_task скасовано")
        return -1

    except Exception as e:
        logger.error(f"❌ Помилка в save_messages_task: {e}")
        try:
            self.retry(exc=e)
        except Exception as retry_error:
            logger.error(f"❌ Не вдалося повторити save_messages_task: {retry_error}")
        return -1

    finally:
        if loop is not None:
            try:
                if not loop.is_closed():
                    loop.close()
            except (RuntimeError, Exception):
                pass