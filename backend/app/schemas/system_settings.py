"""Pydantic schemas for SystemSettings."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SystemSettingsResponse(BaseModel):
    """System settings response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_name: str
    site_short_name: str
    email_notification_enabled: bool = False
    updated_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    created_at: datetime


class SystemSettingsUpdate(BaseModel):
    """Schema for updating system settings. All fields optional."""

    site_name: Optional[str] = Field(None, min_length=1, max_length=100)
    site_short_name: Optional[str] = Field(None, min_length=1, max_length=50)
    email_notification_enabled: Optional[bool] = None


class PublicSiteInfo(BaseModel):
    """Public site info returned without authentication.

    Used by the login page and layout to render the brand name.
    """

    site_name: str
    site_short_name: str
