"""SystemSettings service functions."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_settings import SystemSettings

# Singleton row id used for upsert.
SINGLETON_ID = UUID("00000000-0000-0000-0000-000000000001")


async def get_system_settings(db: AsyncSession) -> SystemSettings:
    """Return the singleton settings row, creating it with defaults if absent."""
    result = await db.execute(
        select(SystemSettings).where(SystemSettings.id == SINGLETON_ID)
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = SystemSettings(
            id=SINGLETON_ID,
            site_name="qloop",
            site_short_name="qloop",
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def update_system_settings(
    db: AsyncSession,
    site_name: Optional[str] = None,
    site_short_name: Optional[str] = None,
    email_notification_enabled: Optional[bool] = None,
    updated_by: Optional[UUID] = None,
) -> SystemSettings:
    """Update the singleton settings row."""
    settings = await get_system_settings(db)
    if site_name is not None:
        settings.site_name = site_name
    if site_short_name is not None:
        settings.site_short_name = site_short_name
    if email_notification_enabled is not None:
        settings.email_notification_enabled = email_notification_enabled
    if updated_by is not None:
        settings.updated_by = updated_by
    await db.commit()
    await db.refresh(settings)
    return settings
