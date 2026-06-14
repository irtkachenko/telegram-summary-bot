"""
summary.py — Celery задача для генерації підсумку чату.

1. Підключається до PostgreSQL та отримує повідомлення.
2. Форматує їх в текст.
3. Надсилає в OpenAI-сумісне API.
4. Відправляє результат власнику бота.
"""
import os
import asyncio
import logging

from app.tasks.app import celery_app
from app.tasks.queries import fetch_messages, get_chat_title
from app.services.openai import generate_summary_with_openai
from app.services.telegram import send_summary_to_user, send_error_to_user

logger = logging.getLogger(__name__)


@celery_app.task(
    name="generate_summary_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def generate_summary_task(self, chat_id: int, period: str, user_id: int):
    """
    Celery задача для генерації підсумку чату.
    """
    loop = None
    bot_token = os.getenv("BOT_TOKEN")

    if not bot_token:
        logger.error("❌ BOT_TOKEN не знайдено в оточенні")
        return

    errors = []

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 1. Отримуємо повідомлення з БД
        messages = loop.run_until_complete(fetch_messages(chat_id, period))

        if not messages:
            chat_title = loop.run_until_complete(get_chat_title(chat_id))
            summary = "📭 За вибраний період немає повідомлень для аналізу."
            error = loop.run_until_complete(
                send_summary_to_user(bot_token, user_id, summary, chat_title)
            )
            if error:
                logger.error(f"❌ Не вдалося надіслати підсумок: {error}")
                errors.append(error)
            logger.info(f"✅ Підсумок для чату {chat_id} надіслано (немає повідомлень)")
            return

        # 2. Форматуємо повідомлення в текст
        formatted_text = "\n\n".join(
            f"👤 {msg['user_name']}: {msg['text']}"
            for msg in messages
        )
        formatted_text = formatted_text[:10000]

        # 3. Генеруємо підсумок через API
        summary, api_error = loop.run_until_complete(
            generate_summary_with_openai(formatted_text)
        )

        # 4. Отримуємо назву чату
        chat_title = loop.run_until_complete(get_chat_title(chat_id))

        if api_error:
            logger.error(f"❌ Помилка API для чату {chat_id}: {api_error}")
            errors.append(api_error)
            loop.run_until_complete(
                send_error_to_user(bot_token, user_id, api_error, chat_title)
            )
        else:
            # 5. Надсилаємо підсумок власнику
            error = loop.run_until_complete(
                send_summary_to_user(bot_token, user_id, summary, chat_title)
            )
            if error:
                logger.error(f"❌ Не вдалося надіслати підсумок: {error}")
                errors.append(error)

        logger.info(f"✅ Задача generate_summary_task завершена для чату {chat_id}")

    except asyncio.CancelledError:
        logger.warning(f"⚠️ Задача для чату {chat_id} скасована")
        return

    except MemoryError:
        logger.error(f"❌ Недостатньо пам'яті для обробки чату {chat_id}")
        try:
            if loop is not None and bot_token:
                loop.run_until_complete(
                    send_error_to_user(
                        bot_token, user_id,
                        "❌ Недостатньо пам'яті для обробки. Спробуйте коротший період."
                    )
                )
        except Exception:
            pass

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Критична помилка в generate_summary_task: {error_msg}")
        errors.append(error_msg)

        if bot_token:
            try:
                error_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(error_loop)
                try:
                    error_loop.run_until_complete(
                        send_error_to_user(bot_token, user_id, error_msg)
                    )
                finally:
                    try:
                        error_loop.close()
                    except Exception:
                        pass
            except Exception:
                logger.error("❌ Не вдалося надіслати повідомлення про помилку")

        try:
            self.retry(exc=e)
        except Exception as retry_error:
            logger.error(f"❌ Не вдалося повторити задачу: {retry_error}")

    finally:
        if loop is not None:
            try:
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                except (RuntimeError, asyncio.CancelledError):
                    pass
            except Exception:
                pass
            finally:
                try:
                    if not loop.is_closed():
                        loop.close()
                except (RuntimeError, Exception):
                    pass