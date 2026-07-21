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
            # 创建站内通知后,异步发送邮件(失败不影响主流程)
            try:
                from sqlalchemy import select as _select
                from app.models.user import User as _User
                from app.services.email_service import notify_user as _notify_user

                user_result = await db.execute(
                    _select(_User).where(_User.id == user_uuid)
                )
                user_obj = user_result.scalar_one_or_none()
                if user_obj and getattr(user_obj, "email", None):
                    # 把 NotificationType 映射到邮件模板键
                    _type_to_template = {
                        "task_assigned": "task_assigned",
                        "review_passed": "review_completed",
                        "release_completed": "release_confirmed",
                    }
                    template_key = _type_to_template.get(notif_type.value)
                    if template_key:
                        # 构造模板上下文(用通知标题/内容作为兜底字段)
                        ctx = {
                            "release_number": title,
                            "review_type": notif_type.value,
                            "triggered_by": "",
                            "result": notif_type.value,
                            "total_score": "",
                            "confirmed_by": "",
                            "stage": notif_type.value,
                        }
                        await _notify_user(user_obj.email, template_key, ctx)
            except Exception as mail_exc:
                logger.warning(
                    "发送邮件通知失败(不影响站内通知): %s", mail_exc
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
