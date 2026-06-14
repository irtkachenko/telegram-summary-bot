"""Tasks (Celery) subpackage."""
from app.tasks.app import celery_app
from app.tasks.summary import generate_summary_task

__all__ = ["celery_app", "generate_summary_task"]
