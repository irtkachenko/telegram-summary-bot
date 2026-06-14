"""Handlers subpackage."""
from app.handlers.errors import router as errors_router
from app.handlers.group import router as group_router
from app.handlers.summary import router as summary_router

__all__ = ["errors_router", "group_router", "summary_router"]