"""
cleanup.py — періодична Celery задача для очищення старих повідомлень.

Видаляє повідомлення старші за MESSAGE_RETENTION_DAYS днів згідно з політикою збереження.
"""
import asyncio
import logging

import asyncpg

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, MESSAGE_RETENTION_DAYS
from app.tasks.app import celery_app

logger = logging.getLogger(__name__)


async def async_cleanup_old_messages():
    """
    Видаляє повідомлення старші за MESSAGE_RETENTION_DAYS днів.
    Також видаляє чати, в яких не залишилось повідомлень.
    """
    conn = None
    try:
        conn = await asyncpg.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, database=DB_NAME,
            timeout=5,
        )
    except Exception as e:
        logger.error(f"❌ БД недоступна для cleanup: {e}")
        return

    try:
        # Видаляємо старі повідомлення
        deleted = await conn.execute(
            """
            DELETE FROM messages
            WHERE created_at < NOW() - $1::interval
            """,
            f"{MESSAGE_RETENTION_DAYS} days",
        )
        deleted_count = int(deleted.split()[-1]) if deleted else 0

        # Видаляємо чати без повідомлень (осиротілі)
        deleted_chats = await conn.execute("""
            DELETE FROM chats
            WHERE chat_id NOT IN (SELECT DISTINCT chat_id FROM messages)
        """)
        deleted_chats_count = int(deleted_chats.split()[-1]) if deleted_chats else 0

        if deleted_count > 0 or deleted_chats_count > 0:
            logger.info(
                f"🧹 Cleanup: видалено {deleted_count} старих повідомлень "
                f"(старше {MESSAGE_RETENTION_DAYS} днів) "
                f"та {deleted_chats_count} порожніх чатів"
            )
        else:
            logger.debug("🧹 Cleanup: старих повідомлень не знайдено")

    except Exception as e:
        logger.error(f"❌ Помилка під час cleanup: {e}")
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass


@celery_app.task(
    name="cleanup_messages_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def cleanup_messages_task(self):
    """Синхронна обгортка Celery для запуску асинхронного cleanup."""
    logger.info("🧹 cleanup_messages_task: запуск очищення старих повідомлень")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(async_cleanup_old_messages())
        return 0
    except Exception as e:
        logger.error(f"❌ Помилка в cleanup_messages_task: {e}")
        self.retry(exc=e)
        return -1
    finally:
        loop.close()