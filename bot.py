"""
bot.py — головний файл Telegram-бота.

Бот працює в режимі Long Polling (без вебхуків).
Ловить всі повідомлення в групах, зберігає їх у БД,
і дає можливість власнику бота генерувати підсумки.
"""

import os
import logging
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, BaseFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

import database as db

# Завантажуємо змінні оточення з .env файлу
load_dotenv()

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфігурація
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0"))

# Перевірка, чи всі змінні задані
if not BOT_TOKEN or BOT_TOKEN == "your_telegram_bot_token_here":
    raise ValueError("❌ BOT_TOKEN не задано або використовується шаблонне значення!")
if BOT_OWNER_ID == 0:
    raise ValueError("❌ BOT_OWNER_ID не задано або дорівнює 0!")

# Створюємо екземпляри бота та диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Глобальний пул з'єднань до БД (заповниться при старті)
db_pool = None


# ===== Callback Data Factories (aiogram 3.x) =====
class ChatSelect(CallbackData, prefix="chat"):
    """
    Callback для вибору чату.
    chat_id — ID вибраного чату.
    """
    chat_id: int


class PeriodSelect(CallbackData, prefix="period"):
    """
    Callback для вибору періоду.
    chat_id — ID чату, для якого генеруємо підсумок.
    period — рядок: "1d", "3d" або "7d".
    """
    chat_id: int
    period: str


# ===== Кастомний фільтр IsBotOwner =====
class IsBotOwner(BaseFilter):
    """
    Фільтр, який пропускає тільки повідомлення від власника бота.
    """

    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id == BOT_OWNER_ID


# ===== Обробник повідомлень у групах =====
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: types.Message):
    """
    Ловить всі повідомлення в групах, де додано бота.
    Зберігає інформацію про чат та повідомлення в БД.
    """
    global db_pool

    chat_id = message.chat.id
    chat_title = message.chat.title or "Unknown Chat"
    user_id = message.from_user.id
    user_name = message.from_user.full_name or "Unknown"
    text = message.text or message.caption or ""

    try:
        async with db_pool.acquire() as conn:
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
    except Exception as e:
        logger.error(f"❌ Помилка при збереженні повідомлення: {e}")


# ===== Команда /summary (тільки в приватному чаті для власника) =====
@dp.message(
    Command("summary"),
    F.chat.type == "private",
    IsBotOwner()
)
async def cmd_summary(message: types.Message):
    """
    Обробник команди /summary.
    Працює тільки в приватному чаті з ботом і тільки для власника.
    Показує список активних чатів для вибору.
    """
    global db_pool

    try:
        # Отримуємо всі чати з БД
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

        # Будуємо інлайн-клавіатуру зі списком чатів
        builder = InlineKeyboardBuilder()
        for row in rows:
            chat_id = row["chat_id"]
            title = row["chat_title"]
            # Використовуємо ChatSelect як callback_data
            builder.button(
                text=title,
                callback_data=ChatSelect(chat_id=chat_id).pack()
            )

        # Розташовуємо кнопки по одній в колонку
        builder.adjust(1)

        await message.answer(
            "📋 Виберіть чат для генерації підсумку:",
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logger.error(f"❌ Помилка при отриманні чатів: {e}")
        await message.answer("❌ Сталася помилка при отриманні списку чатів.")


# ===== Обробник вибору чату =====
@dp.callback_query(ChatSelect.filter())
async def on_chat_selected(callback: types.CallbackQuery, callback_data: ChatSelect):
    """
    Після вибору чату показуємо кнопки для вибору періоду.
    """
    chat_id = callback_data.chat_id

    # Будуємо клавіатуру з вибором періоду
    builder = InlineKeyboardBuilder()
    # Передаємо chat_id та period через PeriodSelect
    builder.button(
        text="1 Day",
        callback_data=PeriodSelect(chat_id=chat_id, period="1d").pack()
    )
    builder.button(
        text="3 Days",
        callback_data=PeriodSelect(chat_id=chat_id, period="3d").pack()
    )
    builder.button(
        text="1 Week",
        callback_data=PeriodSelect(chat_id=chat_id, period="7d").pack()
    )
    builder.adjust(1)

    # Редагуємо повідомлення — прибираємо кнопки вибору чату, додаємо вибір періоду
    await callback.message.edit_text(
        "🕐 Виберіть часовий період:",
        reply_markup=builder.as_markup()
    )

    # Відповідаємо на callback, щоб прибрати "годинник" в Telegram
    await callback.answer()


# ===== Обробник вибору періоду =====
@dp.callback_query(PeriodSelect.filter())
async def on_period_selected(callback: types.CallbackQuery, callback_data: PeriodSelect):
    """
    Після вибору періоду запускаємо Celery-задачу для генерації підсумку.
    """
    chat_id = callback_data.chat_id
    period = callback_data.period
    user_id = callback.from_user.id

    # Змінюємо текст на підтвердження
    await callback.message.edit_text(
        "🔄 Запит прийнято. Збираю повідомлення та генерую підсумок...\n"
        "⏱ Це може зайняти до хвилини. Результат прийде в цей чат."
    )

    # Імпортуємо та запускаємо Celery-задачу
    try:
        from tasks import generate_summary_task
        generate_summary_task.delay(chat_id, period, user_id)
        logger.info(
            f"✅ Запущено задачу для chat_id={chat_id}, period={period}"
        )
    except Exception as e:
        logger.error(f"❌ Помилка запуску Celery задачі: {e}")
        await callback.message.edit_text(
            "❌ Сталася помилка при запуску генерації підсумку."
        )

    await callback.answer()


# ===== Запуск бота =====
async def main():
    """
    Головна функція: ініціалізує БД, запускає бота.
    """
    global db_pool

    logger.info("🚀 Запуск бота...")

    # Створюємо пул з'єднань до БД
    db_pool = await db.get_pool()
    # Створюємо таблиці, якщо їх немає
    await db.init_db(db_pool)

    logger.info("✅ База даних готова. Бот запускається...")

    # Запускаємо long polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())