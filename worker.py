"""Celery entrypoint:  celery -A worker.celery worker --beat --loglevel=info"""
from app.tasks.celery_app import celery  # noqa: F401
import app.tasks.call_tasks  # noqa: F401  (register tasks)
