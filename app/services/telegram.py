"""
telegram.py — надсилання повідомлень через Telegram бота.

Використовує aiogram.Bot для відправки підсумків та повідомлень про помилки.
"""
import logging
import re

from aiogram import Bot
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)


def escape_markdown(text: str) -> str:
    """
    Екранує спеціальні символи MarkdownV2.
    Telegram використовує MarkdownV2, де потрібно екранувати:
    _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", text)


async def send_summary_to_user(
    bot_token: str, user_id: int, summary: str, chat_title: str
) -> str | None:
    """
    Надсилає згенерований підсумок користувачу через Telegram бота.
    Використовує MarkdownV2 з екрануванням спеціальних символів.
    Повертає None при успіху, або текст помилки.
    """
    bot = Bot(token=bot_token)
    try:
        safe_title = escape_markdown(chat_title)
        safe_summary = escape_markdown(summary)

        await bot.send_message(
            chat_id=user_id,
            text=f"📋 *Підсумок чату: {safe_title}*\n\n{safe_summary}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        logger.info(f"✅ Підсумок надіслано користувачу {user_id}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Не вдалося надіслати з MarkdownV2: {e}")
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"📋 Підсумок чату: {chat_title}\n\n{summary}",
            )
            logger.info(f"✅ Підсумок надіслано (без форматування) користувачу {user_id}")
            return None
        except Exception as e2:
            error_msg = str(e2)
            logger.error(f"❌ Помилка при надсиланні повідомлення: {error_msg}")
            return error_msg
    finally:
        try:
            await bot.close()
        except Exception:
            pass


async def send_error_to_user(
    bot_token: str, user_id: int, error_message: str, chat_title: str = ""
):
    """
    Надсилає повідомлення про помилку користувачу.
    """
    bot = Bot(token=bot_token)
    try:
        text = "❌ *Помилка*"
        if chat_title:
            text += f" при обробці чату {escape_markdown(chat_title)}"
        text += f":\n\n{escape_markdown(error_message)}"

        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        logger.info(f"✅ Повідомлення про помилку надіслано користувачу {user_id}")
    except Exception:
        try:
            text = f"❌ Помилка: {error_message}"
            if chat_title:
                text = f"❌ Помилка при обробці чату {chat_title}: {error_message}"
            await bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            logger.error(
                f"❌ Критична помилка: не вдалося надіслати "
                f"повідомлення про помилку: {e}"
            )
    finally:
        try:
            await bot.close()
        except Exception:
            pass
