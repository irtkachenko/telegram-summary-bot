"""
app.py — Celery додаток.

Брокер та бекенд — Redis.
Налаштування для Celery.
"""

from celery import Celery

from app.config import REDIS_URL

celery_app = Celery(
    "tg_summarizer",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# ─── Розклад періодичних задач (Celery Beat) ───────────────────
celery_app.conf.beat_schedule = {
    "save-messages-every-minute": {
        "task": "save_messages_task",
        "schedule": 60.0,  # кожні 60 секунд
        "options": {"expires": 55.0},  # якщо задача не виконалась за 55с — пропустити
    },
    "cleanup-messages-daily": {
        "task": "cleanup_messages_task",
        "schedule": 86400.0,  # раз на добу
        "options": {"expires": 82800.0},  # якщо не виконалась за 23 години — пропустити
    },
}
