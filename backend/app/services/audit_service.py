"""Audit log service."""

import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


def _json_safe(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable values (e.g. UUID) to strings.

    The ``details`` column is a PostgreSQL JSON column; passing UUID objects
    (as produced by Pydantic schemas) raises ``TypeError: Object of type UUID
    is not JSON serializable`` during the INSERT bind.
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return obj


async def create_audit_log(
    db: AsyncSession,
    user_id: Optional[uuid.UUID],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Create an audit log entry.

    Args:
        db: The async database session.
        user_id: The ID of the user who performed the action (if any).
        action: The action performed (e.g. "create_user").
        resource_type: The type of resource affected (e.g. "user").
        resource_id: The ID of the resource affected (as string).
        details: Additional details as a JSON-serializable dict.
        ip_address: The IP address of the requester.

    Returns:
        The created AuditLog object.
    """
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=_json_safe(details) if details is not None else None,
        ip_address=ip_address,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(audit_log)
    return audit_log


async def get_audit_logs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None,
) -> Tuple[List[AuditLog], int]:
    """Get a paginated list of audit logs with optional filtering.

    Args:
        db: The async database session.
        page: Page number (1-based).
        page_size: Number of items per page.
        action: Optional action filter.
        resource_type: Optional resource type filter.
        user_id: Optional user ID filter.

    Returns:
        A tuple of (list of audit logs, total count).
    """
    query = select(AuditLog)

    if action:
        query = query.where(AuditLog.action == action)

    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)

    if user_id:
        query = query.where(AuditLog.user_id == user_id)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = (
        query.offset(offset)
        .limit(page_size)
        .order_by(AuditLog.created_at.desc())
    )

    result = await db.execute(query)
    logs = list(result.scalars().all())

    return logs, total
