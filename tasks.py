"""
tasks.py — вхідна точка для Celery воркера та Celery Beat.

Використовується командами:
    celery -A tasks worker --loglevel=info --pool=solo
    celery -A tasks beat --loglevel=info
"""
from app.tasks import save_messages  # noqa: F401 — періодична задача (save_messages_task)
from app.tasks import summary  # noqa: F401 — задача генерації підсумку (generate_summary_task)
from app.tasks import cleanup  # noqa: F401 — періодична задача (cleanup_messages_task)
from app.tasks.app import celery_app

app = celery_app
