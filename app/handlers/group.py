"""
group.py — обробник повідомлень у групах.
"""
import logging

import asyncpg
from aiogram import F, Router, types

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: types.Message, db_pool: asyncpg.Pool):
    """
    Ловить всі повідомлення в групах, де додано бота.
    Зберігає інформацію про чат та повідомлення в БД.
    db_pool передається через middleware.
    """
    if db_pool is None:
        logger.error("❌ db_pool не ініціалізовано, пропускаємо повідомлення")
        return

    try:
        chat_id = message.chat.id
        chat_title = message.chat.title or "Unknown Chat"
        user_id = message.from_user.id
        user_name = message.from_user.full_name or "Unknown"
        text = message.text or message.caption or ""
        # message.date — naive datetime в UTC від Telegram
        msg_date = message.date
    except AttributeError as e:
        logger.error(f"❌ Помилка отримання даних повідомлення: {e}")
        return

    try:
        async with db_pool.acquire() as conn:
            # UPSERT — оновлюємо або вставляємо інформацію про чат
            await conn.execute("""
                INSERT INTO chats (chat_id, chat_title, updated_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (chat_id)
                DO UPDATE SET chat_title = $2, updated_at = $3
            """, chat_id, chat_title, msg_date)

            # Вставляємо повідомлення
            if text.strip():
                await conn.execute("""
                    INSERT INTO messages (chat_id, user_id, user_name, text, created_at)
                    VALUES ($1, $2, $3, $4, $5)
                """, chat_id, user_id, user_name, text, msg_date)

                logger.info(
                    f"✅ Збережено повідомлення від {user_name} у чаті {chat_title}"
                )
    except asyncpg.PostgresError as e:
        logger.error(f"❌ Помилка БД при збереженні повідомлення: {e}")
    except Exception as e:
        logger.error(f"❌ Неочікувана помилка при збереженні повідомлення: {e}")
