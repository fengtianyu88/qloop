"""System settings API routes.

- GET  /api/system-settings         -> full settings (SUPER_ADMIN only)
- PUT  /api/system-settings          -> update settings (SUPER_ADMIN only)
- GET  /api/system-settings/public  -> public site info (no auth)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.user import SystemRole, User
from app.schemas.system_settings import (
    PublicSiteInfo,
    SystemSettingsResponse,
    SystemSettingsUpdate,
)
from app.services.audit_service import create_audit_log
from app.services.system_settings_service import (
    get_system_settings,
    update_system_settings,
)

router = APIRouter(prefix="/api/system-settings", tags=["system-settings"])

_SUPER_ADMIN = require_roles(SystemRole.SUPER_ADMIN)


@router.get("", response_model=SystemSettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_SUPER_ADMIN),
):
    """Get the current system settings (SUPER_ADMIN only)."""
    settings = await get_system_settings(db)
    return SystemSettingsResponse.model_validate(settings)


@router.put("", response_model=SystemSettingsResponse)
async def update_settings(
    payload: SystemSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_SUPER_ADMIN),
):
    """Update system settings (SUPER_ADMIN only)."""
    settings = await update_system_settings(
        db=db,
        site_name=payload.site_name,
        site_short_name=payload.site_short_name,
        email_notification_enabled=payload.email_notification_enabled,
        updated_by=current_user.id,
    )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="update_system_settings",
        resource_type="system_settings",
        resource_id=str(settings.id),
        details={
            "site_name": payload.site_name,
            "site_short_name": payload.site_short_name,
        },
    )

    return SystemSettingsResponse.model_validate(settings)


@router.get("/public", response_model=PublicSiteInfo)
async def get_public_site_info(
    db: AsyncSession = Depends(get_db),
):
    """Return public site branding info (no authentication required).

    Used by the login page and layout to render the brand name without
    requiring the user to be authenticated first.
    """
    settings = await get_system_settings(db)
    return PublicSiteInfo(
        site_name=settings.site_name,
        site_short_name=settings.site_short_name,
    )
