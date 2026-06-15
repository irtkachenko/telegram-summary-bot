"""
openai.py — генерація підсумків через OpenAI-сумісне API (Groq, OpenAI тощо).

Модель та базовий URL беруться зі змінних оточення:
- OPENAI_API_KEY — API ключ
- OPENAI_API_BASE_URL — базовий URL (для Groq: https://api.groq.com/openai/v1)
- MODEL_NAME — назва моделі (напр. llama-3.3-70b-versatile, gpt-4o-mini)
"""

import logging
from openai import AsyncOpenAI
from app.config import openai_api_base_url, openai_api_key, model_name

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Ти — асистент, який аналізує чати в Telegram та створює структуровані підсумки. "
    "Твоя задача — проаналізувати надані повідомлення з групового чату та створити "
    "короткий, змістовний підсумок українською мовою.\n\n"
    "Формат відповіді:\n"
    "📊 Підсумок чату\n\n"
    "Основні теми обговорення:\n"
    "- Тема 1\n"
    "- Тема 2\n\n"
    "Ключові висновки:\n"
    "- Висновок 1\n"
    "- Висновок 2\n\n"
    "Активні учасники:\n"
    "- @username1\n"
    "- @username2\n\n"
    "Будь лаконічним та інформативним. Використовуй емодзі для кращої читабельності."
)


async def generate_summary_with_openai(messages_text: str) -> tuple:
    """
    Надсилає текст повідомлень в OpenAI-сумісне API та отримує підсумок.

    Повертає (summary: str | None, error: str | None)
    """
    api_key = openai_api_key
    if not api_key or api_key == "your_openai_api_key_here":
        return None, "❌ Не задано OPENAI_API_KEY в .env файлі."

    base_url = openai_api_base_url
    model = model_name

    if not base_url:
        logger.warning(
            "⚠️ OPENAI_API_BASE_URL не задано, "
            "використовується стандартний OpenAI API"
        )

    # Створюємо клієнт
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    try:
        client = AsyncOpenAI(**client_kwargs)
    except Exception as e:
        logger.error(f"❌ Помилка створення OpenAI клієнта: {e}")
        return None, f"❌ Помилка ініціалізації AI клієнта: {e!s}"

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Ось повідомлення з чату для аналізу:\n\n{messages_text}"
                    ),
                },
            ],
            max_tokens=1500,
            temperature=0.7,
        )

        summary = response.choices[0].message.content
        if not summary:
            logger.warning("⚠️ API повернуло порожній підсумок")
            return None, "❌ API повернуло порожній підсумок."

        logger.info("🤖 Підсумок успішно згенеровано")
        return summary, None

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Помилка API: {error_msg}")
        return None, f"❌ Помилка при генерації підсумку: {error_msg}"