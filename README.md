# 🤖 Telegram Summary Bot

Бот збирає повідомлення з Telegram-груп і генерує підсумки через **OpenAI-сумісне API** (Groq, OpenAI тощо).

## Як це працює

1. Додаєте бота в групу — він зберігає всі повідомлення
2. Пишете боту в особисті `/summary`
3. Вибираєте чат → період (1 день, 3 дні, тиждень)
4. Бот надсилає повідомлення в API та повертає підсумок

## Файли

```
.env              # Токени та налаштування
bot.py            # Telegram бот
database.py       # PostgreSQL (asyncpg)
tasks.py          # Фонова генерація підсумків (Celery)
Dockerfile        # Збірка образу
docker-compose.yml # Запуск всіх сервісів
requirements.txt  # Залежності
```

**Де взяти значення:**
- `BOT_TOKEN` — [@BotFather](https://t.me/BotFather)
- `BOT_OWNER_ID` — [@userinfobot](https://t.me/userinfobot)
- `OPENAI_API_KEY` — [console.groq.com](https://console.groq.com) або [platform.openai.com](https://platform.openai.com)
- `OPENAI_API_BASE_URL` — для Groq: `https://api.groq.com/openai/v1`, для OpenAI: залиште пустим
- `MODEL_NAME` — для Groq: `llama3-70b-8192` або `mixtral-8x7b-32768`, для OpenAI: `gpt-4o-mini`

## Запуск

```bash
docker-compose up --build -d
```

## Команди

| Команда | Де працює | Хто може |
|---|---|---|
| `/summary` | Приватний чат з ботом | Тільки власник (BOT_OWNER_ID) |

## Зупинка

```bash
docker-compose down