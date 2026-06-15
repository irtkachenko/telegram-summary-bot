# Telegram Summary Bot

Бот для Telegram, який збирає повідомлення з групових чатів, зберігає їх у PostgreSQL і генерує підсумки через OpenAI-сумісне API (Groq / OpenAI).

## Як це працює

1. Додайте бота в Telegram-групу — він автоматично зберігає всі повідомлення в базу даних.
2. Напишіть боту в особисті повідомлення команду `/summary`.
3. Виберіть чат і період (1 день, 3 дні, тиждень).
4. Бот надсилає зібрані повідомлення в OpenAI-сумісне API та повертає структурований підсумок.

## Структура проекту

```
app/
├── config.py          # читання .env, валідація
├── main.py            # точка входу: Bot, Dispatcher, db_pool, middleware
│
├── db/
│   ├── pool.py        # asyncpg.create_pool()
│   └── models.py      # CREATE TABLE (chats, messages)
│
├── filters/
│   └── owner.py       # is_bot_owner() — перевірка власника
│
├── handlers/
│   ├── errors.py      # глобальний error handler
│   ├── group.py       # збереження повідомлень з груп
│   └── summary.py     # /summary + клавіатури
│
├── services/
│   ├── openai.py      # генерація підсумку через Groq/OpenAI
│   └── telegram.py    # надсилання підсумків користувачу
│
└── tasks/
    ├── app.py         # Celery додаток (Redis)
    ├── queries.py     # запити до БД
    └── summary.py     # generate_summary_task
```

## Запуск

### Docker Compose

```bash
docker-compose up --build -d     # Запустити
docker-compose down              # Зупинити
```

Запускає чотири сервіси: bot, worker (Celery), postgres, redis.

### Локально

Спочатку запустіть PostgreSQL і Redis. Потім в окремих терміналах:

```bash
python app/main.py                                        # Бот
celery -A tasks worker --loglevel=info --pool=solo        # Celery воркер
```

## Команди

| Команда | Де працює | Хто може |
|---------|-----------|----------|
| `/summary` | Приватний чат | Тільки власник |