"""Notification service."""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType


async def create_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    type: NotificationType,
    title: str,
    content: str,
    link_url: Optional[str] = None,
) -> Notification:
    """Create a notification for a user.

    Args:
        db: The async database session.
        user_id: The recipient user ID.
        type: The notification type.
        title: The notification title.
        content: The notification content.
        link_url: Optional URL to link to.

    Returns:
        The created Notification object.
    """
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        content=content,
        link_url=link_url,
        is_read=False,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return notification


async def get_user_notifications(
    db: AsyncSession,
    user_id: uuid.UUID,
    unread_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Notification], int]:
    """Get a paginated list of notifications for a user.

    Args:
        db: The async database session.
        user_id: The user ID.
        unread_only: If True, only return unread notifications.
        page: Page number (1-based).
        page_size: Number of items per page.

    Returns:
        A tuple of (list of notifications, total count).
    """
    query = select(Notification).where(Notification.user_id == user_id)

    if unread_only:
        query = query.where(Notification.is_read == False)  # noqa: E712

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = (
        query.offset(offset)
        .limit(page_size)
        .order_by(Notification.created_at.desc())
    )

    result = await db.execute(query)
    notifications = list(result.scalars().all())

    return notifications, total


async def mark_as_read(
    db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[Notification]:
    """Mark a notification as read.

    Only the notification's owner can mark it as read.

    Args:
        db: The async database session.
        notification_id: The notification ID.
        user_id: The user ID (for ownership verification).

    Returns:
        The updated Notification object, or ``None`` if not found.
    """
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        return None

    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification


async def mark_all_as_read(db: AsyncSession, user_id: uuid.UUID) -> int:
    """把指定用户的所有未读通知标记为已读。

    Args:
        db: The async database session.
        user_id: The user ID.

    Returns:
        被标记为已读的通知条数。
    """
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    await db.commit()
    return result.rowcount or 0
