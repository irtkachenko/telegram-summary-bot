# 🤖 Telegram Summary Bot

Бот збирає повідомлення з Telegram-груп і генерує підсумки через **OpenAI-сумісне API** (Groq, OpenAI тощо).

## Як це працює

1. Додаєте бота в групу — він зберігає всі повідомлення
2. Пишете боту в особисті `/summary`
3. Вибираєте чат → період (1 день, 3 дні, тиждень)
4. Бот надсилає повідомлення в API та повертає підсумок

## Структура проєкту

```
telegram-summary-bot/
├── app/                           # 👈 основний код
│   ├── __init__.py                # пакет
│   ├── __main__.py                # точка входу (python -m app)
│   ├── config.py                  # конфігурація + валідація .env
│   ├── bot_instance.py            # екземпляри Bot, Dispatcher, db_pool
│   │
│   ├── filters/                   # кастомні фільтри Telegram
│   │   ├── __init__.py
│   │   └── owner.py               # IsBotOwner — тільки власник
│   │
│   ├── keyboards/                 # інлайн-клавіатури
│   │   ├── __init__.py
│   │   └── callbacks.py           # ChatSelect, PeriodSelect + builder
│   │
│   ├── db/                        # PostgreSQL (asyncpg)
│   │   ├── __init__.py
│   │   ├── pool.py                # створення пулу з'єднань
│   │   └── models.py              # схема БД (chats, messages)
│   │
│   ├── handlers/                  # обробники Telegram-апдейтів
│   │   ├── __init__.py
│   │   ├── errors.py              # глобальний error handler
│   │   ├── group.py               # збереження повідомлень з груп
│   │   └── summary.py             # /summary + вибір чату/періоду
│   │
│   ├── services/                  # зовнішні API
│   │   ├── __init__.py
│   │   ├── openai.py              # генерація підсумків через Groq/OpenAI
│   │   └── telegram.py            # надсилання підсумків користувачу
│   │
│   └── tasks/                     # Celery (фонові задачі)
│       ├── __init__.py
│       ├── app.py                 # Celery додаток (Redis)
│       ├── queries.py             # запити до БД для воркера
│       └── summary.py             # задача generate_summary_task
│
├── .env                    # токени та налаштування
├── .env.example            # шаблон .env
├── bot.py                  # вхідна точка для бота
├── tasks.py                # вхідна точка для Celery
├── Dockerfile              # збірка образу
├── docker-compose.yml      # оркестрація всіх сервісів
├── requirements.txt        # залежності
└── README.md               # цей файл
```

## Файли конфігурації

```
.env              # Токени та налаштування
bot.py            # Вхідна точка бота (→ app/__main__.py)
tasks.py          # Вхідна точка Celery (→ app/tasks/ )
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
- `DB_HOST` — для Docker: `postgres`, для локального запуску: `localhost`
- `REDIS_URL` — для Docker: `redis://redis:6379/0`, для локального запуску: `redis://localhost:6379/0`

## Запуск

```bash
docker-compose up --build -d
```

## Зупинка

```bash
docker-compose down
```

## Команди

| Команда | Де працює | Хто може |
|---------|-----------|----------|
| `/summary` | Приватний чат з ботом | Тільки власник (BOT_OWNER_ID) |