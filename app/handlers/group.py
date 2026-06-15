"""
group.py — обробник повідомлень у групах.

Повідомлення пишуться не напряму в PostgreSQL, а в Redis-чергу.
Celery beat кожну хвилину збирає всі накопичені повідомлення
та записує їх batch-ом у БД.
"""
import logging
from datetime import timezone

from aiogram import F, Router, types

from app.services.redis import push_message

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: types.Message):
    """
    Ловить всі повідомлення в групах, де додано бота.
    Зберігає повідомлення в Redis-чергу (не напряму в БД).
    """
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        user_name = message.from_user.full_name or "Unknown"
        text = message.text or message.caption or ""

        if not text.strip():
            return

        # Конвертуємо naive datetime в ISO-рядок з UTC
        # Telegram повертає naive datetime, але завжди в UTC
        msg_date = message.date.replace(tzinfo=timezone.utc).isoformat()

        chat_title = message.chat.title or message.chat.full_name or f"Chat #{chat_id}"

        await push_message(
            chat_id=chat_id,
            user_id=user_id,
            user_name=user_name,
            text=text,
            created_at=msg_date,
            chat_title=chat_title,
        )

        logger.info(
            f"📨 Повідомлення від {user_name} у чаті {chat_id} "
            f"відправлено в Redis-чергу"
        )

    except AttributeError as e:
        logger.error(f"❌ Помилка отримання даних повідомлення: {e}")
    except Exception as e:
        logger.error(f"❌ Неочікувана помилка при обробці повідомлення: {e}")