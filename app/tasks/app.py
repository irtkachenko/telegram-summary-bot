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