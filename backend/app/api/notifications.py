"""Notification API routes."""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_sse
from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.services.notification_service import (
    get_user_notifications,
    mark_as_read,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    """Schema for notification responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    type: NotificationType
    title: str
    content: str
    is_read: bool
    link_url: Optional[str] = None
    created_at: datetime


@router.get("", response_model=PaginatedResponse[NotificationResponse])
async def list_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current user's notifications."""
    notifications, total = await get_user_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse[NotificationResponse].create(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a notification as read."""
    notification = await mark_as_read(
        db=db,
        notification_id=notification_id,
        user_id=current_user.id,
    )
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return NotificationResponse.model_validate(notification)


@router.get("/stream")
async def stream_notifications(
    current_user: User = Depends(get_current_user_sse),
    db: AsyncSession = Depends(get_db),
):
    """SSE 端点:实时推送当前用户的新通知。

    前端用 EventSource 接收,每 5 秒轮询一次数据库,推送自上次检查后的新通知。
    认证通过 query 参数 ?token=xxx 传递(EventSource 不支持自定义 header)。
    """
    async def event_generator():
        # 用 naive UTC 时间戳比较(数据库字段为 timezone-aware,需统一)
        last_check = datetime.utcnow()
        while True:
            try:
                result = await db.execute(
                    select(Notification)
                    .where(
                        Notification.user_id == current_user.id,
                        Notification.created_at > last_check,
                    )
                    .order_by(Notification.created_at.desc())
                )
                new_notifications = result.scalars().all()
            except Exception as exc:  # 数据库异常推送错误事件后退出
                err = {"error": str(exc)}
                yield f"data: {json.dumps(err)}\n\n"
                break

            for notif in new_notifications:
                notif_type = notif.type.value if hasattr(notif.type, "value") else str(notif.type)
                data = {
                    "id": str(notif.id),
                    "title": notif.title,
                    "content": notif.content,
                    "type": notif_type,
                    "link_url": notif.link_url,
                    "created_at": notif.created_at.isoformat() if notif.created_at else None,
                }
                yield f"data: {json.dumps(data)}\n\n"
                # 更新 last_check 为最新一条通知时间(注意时区)
                last_check = notif.created_at.replace(tzinfo=None) if notif.created_at else last_check

            # 心跳注释,保持连接
            yield ": heartbeat\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
