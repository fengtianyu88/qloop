"""Celery task that creates a notification record asynchronously."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from app.database import async_session
from app.models.notification import NotificationType
from app.services.notification_service import create_notification
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run a coroutine in a dedicated event loop and return its result."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="send_notification")
def send_notification(
    user_id: str,
    type: str,
    title: str,
    content: str,
    link_url: Optional[str] = None,
) -> dict:
    """Create an in-app notification for a user.

    Args:
        user_id: The recipient user ID (string UUID).
        type: A :class:`NotificationType` value (e.g. ``"review_passed"``).
        title: The notification title.
        content: The notification body text.
        link_url: Optional URL the notification links to.

    Returns:
        A dict with ``notification_id`` (str) and ``status`` ("ok" or
        "error"). On error an ``error`` field is included.
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, TypeError) as exc:
        logger.error("Invalid user_id '%s': %s", user_id, exc)
        return {"notification_id": None, "status": "error", "error": "Invalid user_id"}

    try:
        notif_type = NotificationType(type)
    except ValueError as exc:
        logger.error("Unknown notification type '%s': %s", type, exc)
        return {
            "notification_id": None,
            "status": "error",
            "error": f"Unknown notification type: {type}",
        }

    async def _run() -> dict:
        async with async_session() as db:
            notification = await create_notification(
                db=db,
                user_id=user_uuid,
                type=notif_type,
                title=title,
                content=content,
                link_url=link_url,
            )
            return {
                "notification_id": str(notification.id),
                "status": "ok",
            }

    try:
        return _run_async(_run())
    except Exception as exc:  # noqa: BLE001
        logger.exception("send_notification failed: %s", exc)
        return {
            "notification_id": None,
            "status": "error",
            "error": str(exc),
        }
