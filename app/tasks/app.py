"""
app.py — Celery додаток.

Брокер та бекенд — Redis.
Налаштування для Celery.
"""
import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

celery_app = Celery(
    "tg_summarizer",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
