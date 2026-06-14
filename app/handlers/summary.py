"""
summary.py — обробник команди /summary.

Працює тільки в приватному чаті з ботом і тільки для власника.
Показує список чатів → вибір періоду → запуск Celery задачі.
"""

import asyncpg
from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command

from app.config import logger
from app.filters import IsBotOwner
from app.keyboards import ChatSelect, PeriodSelect, chat_list_keyboard, period_keyboard

router = Router()


@router.message(
    Command("summary"),
    F.chat.type == "private",
    IsBotOwner()
)
async def cmd_summary(message: types.Message, db_pool: asyncpg.Pool):
    """
    Обробник команди /summary.
    Показує список активних чатів для вибору.
    db_pool передається через middleware.
    """
    if db_pool is None:
        await message.answer("❌ База даних ще не підключена. Зачекайте та спробуйте знову.")
        return

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT chat_id, chat_title FROM chats ORDER BY updated_at DESC"
            )

        if not rows:
            await message.answer(
                "😕 Немає збережених чатів. "
                "Додайте бота в групу і надішліть туди повідомлення."
            )
            return

        keyboard = chat_list_keyboard(rows)
        await message.answer(
            "📋 Виберіть чат для генерації підсумку:",
            reply_markup=keyboard.as_markup()
        )

    except asyncpg.PostgresError as e:
        logger.error(f"❌ Помилка БД при отриманні чатів: {e}")
        await message.answer("❌ Сталася помилка бази даних при отриманні списку чатів.")
    except Exception as e:
        logger.error(f"❌ Помилка при отриманні чатів: {e}")
        await message.answer("❌ Сталася помилка при отриманні списку чатів.")


@router.callback_query(ChatSelect.filter())
async def on_chat_selected(callback: types.CallbackQuery, callback_data: ChatSelect):
    """
    Після вибору чату показуємо кнопки для вибору періоду.
    """
    try:
        chat_id = callback_data.chat_id
        keyboard = period_keyboard(chat_id)

        await callback.message.edit_text(
            "🕐 Виберіть часовий період:",
            reply_markup=keyboard.as_markup()
        )
        await callback.answer()

    except TelegramBadRequest as e:
        logger.error(f"❌ Помилка редагування повідомлення: {e}")
        try:
            await callback.answer("❌ Помилка. Спробуйте ще раз /summary")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"❌ Помилка при виборі чату: {e}")
        try:
            await callback.answer("❌ Сталася помилка")
        except Exception:
            pass


@router.callback_query(PeriodSelect.filter())
async def on_period_selected(callback: types.CallbackQuery, callback_data: PeriodSelect):
    """
    Після вибору періоду запускаємо Celery-задачу для генерації підсумку.
    """
    try:
        chat_id = callback_data.chat_id
        period = callback_data.period
        user_id = callback.from_user.id

        await callback.message.edit_text(
            "🔄 Запит прийнято. Збираю повідомлення та генерую підсумок...\n"
            "⏱ Це може зайняти до хвилини. Результат прийде в цей чат."
        )

        try:
            from tasks import generate_summary_task
            generate_summary_task.delay(chat_id, period, user_id)
            logger.info(f"✅ Запущено задачу для chat_id={chat_id}, period={period}")
        except ImportError as e:
            logger.error(f"❌ Помилка імпорту tasks: {e}")
            await callback.message.edit_text(
                "❌ Помилка: модуль tasks не знайдено. Перевірте файл tasks.py"
            )
        except Exception as e:
            logger.error(f"❌ Помилка запуску Celery задачі: {e}")
            await callback.message.edit_text(
                "❌ Сталася помилка при запуску генерації підсумку. "
                "Перевірте, чи працює Redis та Celery worker."
            )

        await callback.answer()

    except TelegramBadRequest as e:
        logger.error(f"❌ Помилка редагування повідомлення: {e}")
        try:
            await callback.answer("❌ Помилка. Спробуйте ще раз /summary")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"❌ Помилка при виборі періоду: {e}")
        try:
            await callback.answer("❌ Сталася помилка")
        except Exception:
            pass