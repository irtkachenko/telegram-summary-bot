"""
group.py — обробник повідомлень у групах.

Ловить всі повідомлення в групах, де додано бота,
та зберігає їх у PostgreSQL.
"""
import logging

from aiogram import F, types
import asyncpg

from app import bot_instance

logger = logging.getLogger(__name__)


@bot_instance.dp.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: types.Message):
    """
    Ловить всі повідомлення в групах, де додано бота.
    Зберігає інформацію про чат та повідомлення в БД.
    """
    if bot_instance.db_pool is None:
        logger.error("❌ db_pool не ініціалізовано, пропускаємо повідомлення")
        return

    try:
        chat_id = message.chat.id
        chat_title = message.chat.title or "Unknown Chat"
        user_id = message.from_user.id
        user_name = message.from_user.full_name or "Unknown"
        text = message.text or message.caption or ""
    except AttributeError as e:
        logger.error(f"❌ Помилка отримання даних повідомлення: {e}")
        return

    try:
        async with bot_instance.db_pool.acquire() as conn:
            # UPSERT — оновлюємо або вставляємо інформацію про чат
            await conn.execute("""
                INSERT INTO chats (chat_id, chat_title, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (chat_id)
                DO UPDATE SET chat_title = $2, updated_at = NOW()
            """, chat_id, chat_title)

            # Вставляємо повідомлення
            if text.strip():
                await conn.execute("""
                    INSERT INTO messages (chat_id, user_id, user_name, text, created_at)
                    VALUES ($1, $2, $3, $4, NOW())
                """, chat_id, user_id, user_name, text)

                logger.info(
                    f"✅ Збережено повідомлення від {user_name} у чаті {chat_title}"
                )
    except asyncpg.PostgresError as e:
        logger.error(f"❌ Помилка БД при збереженні повідомлення: {e}")
    except Exception as e:
        logger.error(f"❌ Неочікувана помилка при збереженні повідомлення: {e}")