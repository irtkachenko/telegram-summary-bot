"""
tasks.py — вхідна точка для Celery воркера.

Використовується командою:
    celery -A tasks worker --loglevel=info --pool=solo
"""
from app.tasks.app import celery_app
from app.tasks import summary  # noqa: F401 — реєструємо задачу

app = celery_app