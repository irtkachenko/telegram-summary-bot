"""Handlers subpackage."""
# Імпортуємо обробники, щоб вони зареєструвались у диспетчері
from app.handlers import errors, group, summary

__all__ = ["errors", "group", "summary"]