"""Celery application instance for asynchronous background tasks.

Both the broker and the result backend use Redis (configured via
``settings.REDIS_URL``). Task modules are listed in ``include`` so their
``@celery_app.task`` decorators are registered when a worker starts.
"""

from celery import Celery

from app.config import settings

# Create the Celery instance. Both broker and backend use Redis.
celery_app = Celery(
    "bms_sox",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.review_tasks",
        "app.tasks.notification_tasks",
        "app.tasks.email_tasks",
    ],
)

# Configuration.
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    # Hard limit (seconds) after which a task is forcibly terminated.
    task_time_limit=600,
    # Soft limit gives the task a chance to clean up before the hard limit.
    task_soft_time_limit=540,
)
