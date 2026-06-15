"""
save_messages.py — періодична Celery задача для збереження повідомлень.

Кожну хвилину (через Celery Beat):
  1. Отримує всі ключі черги повідомлень з Redis.
  2. Для кожного ключа atomically витягує всі повідомлення.
  3. Записує їх batch-ом в PostgreSQL:
     - upsert в таблицю chats
     - insert в таблицю messages
"""
import asyncio
import logging
from datetime import datetime, timezone

import asyncpg

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.services.redis import (
    get_all_queue_keys,
    pop_all_messages,
)
from app.tasks.app import celery_app

logger = logging.getLogger(__name__)

# Розмір batch-у для INSERT
BATCH_SIZE = 100


async def async_flush_messages():
    """
    Асинхронна логіка:
      1. Ініціалізуємо Redis клієнт (якщо ще не ініціалізовано)
      2. Отримуємо всі ключі черги (messages:queue:*)
      3. Для кожного ключа atomically дістаємо повідомлення
      4. Розбиваємо на batch-и та записуємо в БД
    """
    # 0. Ініціалізуємо Redis (цей код виконується в Celery worker, не в боті)
    from app.services.redis import init_redis as _init_redis
    await _init_redis()

    # 1. Отримуємо всі ключі
    keys = await get_all_queue_keys()
    if not keys:
        logger.debug("⏳ Черга повідомлень порожня, пропускаємо")
        return

    logger.info(f"🔄 Знайдено {len(keys)} черг для обробки")

    # 2. Для кожного ключа — atomically pop+delete
    all_messages: list[dict] = []

    # Спочатку збираємо всі повідомлення з черг транзакційно
    for key in keys:
        messages = await pop_all_messages(key)
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
            # Назва чату може бути відсутня в повідомленні з черги
            # Тому використовуємо fallback
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

            # asyncpg не підтримує executemany напряму з RETURNING?
            # Зробимо через цикл (всередині транзакції це нормально)
            async with conn.transaction():
                for msg in batch:
                    try:
                        # Парсимо created_at з ISO-рядка
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
                        # Продовжуємо з наступним

            logger.info(f"✅ Записано batch {i + 1}–{i + len(batch)} з {len(all_messages)}")

        logger.info(f"✅ Успішно збережено {len(all_messages)} повідомлень у PostgreSQL")

    except Exception as e:
        logger.error(f"❌ Помилка batch-запису в БД: {e}")
    finally:
        try:
            await conn.close()
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
