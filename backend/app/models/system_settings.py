"""SystemSettings model: stores runtime-configurable site branding."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SystemSettings(Base):
    """Singleton row storing global system settings.

    Only one row is expected (id = SINGLETON_ID). Updated via the
    /api/system-settings endpoints by super_admin users.
    """

    __tablename__ = "system_settings"

    # Singleton primary key (fixed UUID to make the row easy to upsert)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    )

    # Branding
    site_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="qloop"
    )
    site_short_name: Mapped[str] = mapped_column(
        String(50), nullable=False, default="qloop"
    )

    # 邮件通知总开关(超管可设置)
    email_notification_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Audit
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
