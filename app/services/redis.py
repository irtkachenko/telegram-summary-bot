"""
redis.py — прямий доступ до Redis (не через Celery).

Використовується для:
  1. Буферизації вхідних повідомлень з Telegram в Redis List.
  2. Атомарного отримання та очищення черги для batch-запису в PostgreSQL.

Бібліотека: redis.asyncio (входить до redis-py >= 4.0.0).
"""

import asyncio
import json
import logging
import redis.asyncio as aioredis
from app.config import REDIS_URL

logger = logging.getLogger(__name__)

# Глобальний async Redis клієнт (пул з'єднань створюється автоматично)
redis_client: aioredis.Redis | None = None

# Префікс для ключів черги повідомлень
MESSAGE_QUEUE_PREFIX = "messages:queue:"


async def init_redis():
    """Ініціалізує глобальний Redis клієнт."""
    global redis_client
    if redis_client is None:
        try:
            redis_client = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,  # автоматично декодувати bytes → str
                socket_keepalive=True,
                health_check_interval=30,
            )
            await redis_client.ping()
            logger.info("✅ Пряме з'єднання з Redis встановлено")
        except Exception as e:
            logger.error(f"❌ Помилка підключення до Redis: {e}")
            raise


async def close_redis():
    """Закриває глобальний Redis клієнт."""
    global redis_client
    if redis_client is not None:
        try:
            await redis_client.aclose()
            logger.info("🔌 З'єднання з Redis закрито")
        except Exception as e:
            logger.error(f"❌ Помилка закриття Redis: {e}")
        finally:
            redis_client = None


async def push_message(
    chat_id: int,
    user_id: int,
    user_name: str,
    text: str,
    created_at: str,
):
    """
    Додає повідомлення в кінець Redis List для заданого чату.

    Формат збереження — JSON-рядок.
    """
    if redis_client is None:
        logger.error("❌ Redis клієнт не ініціалізовано")
        return

    key = f"{MESSAGE_QUEUE_PREFIX}{chat_id}"
    message_data = json.dumps({
        "chat_id": chat_id,
        "user_id": user_id,
        "user_name": user_name,
        "text": text,
        "created_at": created_at,
    })

    try:
        await redis_client.rpush(key, message_data)
        logger.debug(f"📨 Повідомлення додано в Redis: {key}")
    except Exception as e:
        logger.error(f"❌ Помилка push_message до Redis: {e}")


async def pop_all_messages(key: str) -> list[dict]:
    """
    Атомарно отримує всі повідомлення з черги та очищає її.

    Використовує MULTI/EXEC (транзакцію):
      1. LRANGE key 0 -1
      2. DEL key
    Повертає список словників, або порожній список, якщо черга порожня.
    """
    if redis_client is None:
        logger.error("❌ Redis клієнт не ініціалізовано")
        return []

    try:
        pipe = redis_client.pipeline(transaction=True)
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

    except Exception as e:
        logger.error(f"❌ Помилка pop_all_messages з Redis: {e}")
        return []


async def get_all_queue_keys() -> list[str]:
    """
    Повертає список усіх ключів черги повідомлень (SCAN 0 MATCH messages:queue:*).
    """
    if redis_client is None:
        logger.error("❌ Redis клієнт не ініціалізовано")
        return []

    try:
        cursor = 0
        keys = []
        while True:
            cursor, batch = await redis_client.scan(
                cursor=cursor,
                match=f"{MESSAGE_QUEUE_PREFIX}*",
                count=100,
            )
            keys.extend(batch)
            if cursor == 0:
                break

        return keys

    except Exception as e:
        logger.error(f"❌ Помилка get_all_queue_keys з Redis: {e}")
        return []


async def get_queue_length(chat_id: int | None = None) -> int:
    """
    Повертає кількість повідомлень у черзі.
    Якщо chat_id вказано — тільки для конкретного чату.
    Якщо None — для всіх чатів.
    """
    if redis_client is None:
        return 0

    try:
        if chat_id is not None:
            key = f"{MESSAGE_QUEUE_PREFIX}{chat_id}"
            return await redis_client.llen(key)
        else:
            keys = await get_all_queue_keys()
            if not keys:
                return 0
            lengths = await asyncio.gather(
                *[redis_client.llen(k) for k in keys],
                return_exceptions=True,
            )
            total = sum(
                v for v in lengths if isinstance(v, int)
            )
            return total

    except Exception as e:
        logger.error(f"❌ Помилка get_queue_length: {e}")
        return 0