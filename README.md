# Telegram Summary Bot

Бот для Telegram, який записує повідомлення з груп у PostgreSQL і генерує підсумки через Groq (OpenAI-сумісне API).  
Використовує Redis як буфер — повідомлення спочатку потрапляють у Redis, а раз на хвилину Celery записує їх пачкою в базу.

## Як це працює

1. Додайте бота в Telegram-групу — він зберігає всі повідомлення.
2. Напишіть боту в особисті повідомлення `/summary`.
3. Виберіть чат і період (1 день, 3 дні, тиждень).
4. Бот надсилає повідомлення в Groq API та повертає структурований підсумок.

## Структура проєкту

```
telegram-summary-bot/
├── app/
│   ├── main.py              # точка входу (бот, диспетчер, підключення)
│   ├── config.py            # змінні оточення з .env
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── pool.py          # пул з'єднань PostgreSQL
│   │   └── models.py        # створення таблиць chats / messages
│   │
│   ├── filters/
│   │   ├── __init__.py
│   │   └── owner.py         # фільтр — тільки власник бота
│   │
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── group.py         # обробка повідомлень у групах → Redis
│   │   ├── summary.py       # команда /summary → вибір чату і періоду
│   │   └── errors.py        # глобальний перехоплювач помилок
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── redis.py         # push/pop у Redis, create_standalone_client()
│   │   ├── openai.py        # генерація підсумку через Groq API
│   │   └── telegram.py      # надсилання результату користувачу
│   │
│   └── tasks/
│       ├── __init__.py
│       ├── app.py           # Celery додаток + розклад (beat)
│       ├── save_messages.py # перенос Redis → PostgreSQL щохвилини
│       ├── summary.py       # генерація підсумку (Celery задача)
│       └── queries.py       # SQL-запити для summary
│
├── tasks.py                 # точка входу для Celery воркера
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

## Архітектура збереження повідомлень

```
Telegram → group.py → push_message(chat_id, text, user, chat_title)
                  ↓
            Redis List (messages:queue:*)
                  ↓  (раз на хвилину, Celery Beat)
            save_messages_task
                  ↓
            PostgreSQL (chats + messages)
```

- Повідомлення миттєво пишуться в Redis — бот не чекає на базу.
- Celery-задача `save_messages_task` раз на хвилину забирає всі накопичені повідомлення і вставляє їх в PostgreSQL одним batch-запитом (`executemany`).
- Якщо PostgreSQL недоступний — Redis не очищується, дані не губляться.
- Для Celery використовується ізольований Redis-клієнт, щоб уникнути помилок `Event loop is closed`.

## Запуск

### Docker Compose

```bash
docker-compose up --build -d     # запустити всі сервіси
docker-compose down              # зупинити
```

Запускає шість контейнерів:
- **postgres** — база даних PostgreSQL для зберігання повідомлень і чатів
- **redis** — Redis-буфер для черги повідомлень і брокер Celery
- **bot** — Telegram-бот (aiogram long polling)
- **celery_worker** — Celery воркер для фонових задач (збереження повідомлень, генерація підсумків)
- **celery_beat** — Celery Beat для періодичного запуску задач (раз на хвилину)
- **adminer** — веб-інтерфейс для адміністрування PostgreSQL (доступний на http://localhost:8080)

### Локально

Спочатку запустіть PostgreSQL і Redis. Потім в окремих терміналах:

```bash
python app/main.py                                        # бот
celery -A tasks worker --loglevel=info --pool=solo        # Celery воркер
celery -A tasks beat --loglevel=info                      # Celery Beat (розклад)
```

## Команди

| Команда | Де працює | Хто може |
|---------|-----------|----------|
| `/summary` | Приватний чат з ботом | Тільки власник |

## Змінні оточення

| Змінна | Опис |
|--------|------|
| `BOT_TOKEN` | Токен Telegram бота |
| `BOT_OWNER_ID` | ID власника (число) |
| `OPENAI_API_KEY` | Ключ Groq (або OpenAI) |
| `OPENAI_API_BASE_URL` | Базовий URL API (для Groq: `https://api.groq.com/openai/v1`) |
| `MODEL_NAME` | Модель (за замовчуванням `llama3-8b-8192`) |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | PostgreSQL |
| `REDIS_URL` | Redis (за замовчуванням `redis://redis:6379/0`) |