"""Audit log API routes."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles
from app.models.user import SystemRole, User
from app.schemas.common import PaginatedResponse
from app.services.audit_service import get_audit_logs

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    """Schema for audit log responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime


@router.get("", response_model=PaginatedResponse[AuditLogResponse])
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    user_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(SystemRole.ADMIN, SystemRole.SUPER_ADMIN)
    ),
):
    """Get a paginated list of audit logs (ADMIN, SUPER_ADMIN only).

    Filters:
        - action: Exact match on action.
        - resource_type: Exact match on resource type.
        - user_id: Exact match on user ID.
    """
    logs, total = await get_audit_logs(
        db=db,
        page=page,
        page_size=page_size,
        action=action,
        resource_type=resource_type,
        user_id=user_id,
    )
    return PaginatedResponse[AuditLogResponse].create(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )
