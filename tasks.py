"""
tasks.py — вхідна точка для Celery воркера.

Використовується командою:
    celery -A tasks worker --loglevel=info --pool=solo
"""
from app.tasks import summary  # noqa: F401 — реєструємо задачу
from app.tasks.app import celery_app

app = celery_app
