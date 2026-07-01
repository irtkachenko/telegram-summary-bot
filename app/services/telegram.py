"""
telegram.py — надсилання повідомлень через Telegram бота.

Використовує aiogram.Bot для відправки підсумків та повідомлень про помилки.
"""
import html
import logging
from aiogram import Bot
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)


def escape_html(text: str) -> str:
    """
    Екранує небезпечні для HTML символи за допомогою html.escape.
    Telegram HTML дозволяє теги <b>, <i>, <code>, <pre>, <a> тощо.
    Екранувати потрібно лише: < > & "
    """
    return html.escape(text, quote=True)


async def send_summary_to_user(
    bot_token: str, user_id: int, summary: str, chat_title: str
) -> str | None:
    """
    Надсилає згенерований підсумок користувачу через Telegram бота.
    Використовує HTML-форматування з екрануванням лише небезпечних символів.
    Повертає None при успіху, або текст помилки.
    """
    bot = Bot(token=bot_token)
    try:
        safe_title = escape_html(chat_title)

        await bot.send_message(
            chat_id=user_id,
            text=f"📋 <b>Підсумок чату: {safe_title}</b>\n\n{summary}",
            parse_mode=ParseMode.HTML,
        )
        logger.info(f"✅ Підсумок надіслано користувачу {user_id}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Не вдалося надіслати з HTML: {e}")
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
        text = "❌ <b>Помилка</b>"
        if chat_title:
            text += f" при обробці чату {escape_html(chat_title)}"
        text += f":\n\n{escape_html(error_message)}"

        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.HTML,
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