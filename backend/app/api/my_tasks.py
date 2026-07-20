"""My tasks API - todo and done lists for the current user."""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import (
    Project,
    Release,
    ReleaseStatus,
    Version,
)
from app.models.user import User
from app.services.audit_service import create_audit_log  # noqa: F401


router = APIRouter(prefix="/api/my-tasks", tags=["my-tasks"])


class MyTaskItem(BaseModel):
    """A todo/done item for the current user."""

    model_config = ConfigDict(from_attributes=True)

    release_id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    project_name: Optional[str] = None
    version_id: Optional[uuid.UUID] = None
    version_number: Optional[str] = None
    release_number: Optional[int] = None
    status: ReleaseStatus
    change_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Role of the current user on this release
    my_role: Optional[str] = None
    # Names for display
    developer_name: Optional[str] = None
    tester_name: Optional[str] = None
    expert_name: Optional[str] = None
    pm_name: Optional[str] = None


TODO_STATUSES = [
    ReleaseStatus.CODE_PENDING_REVIEW,
    ReleaseStatus.TEST_PENDING_REVIEW,
    ReleaseStatus.EXPERT_PENDING_REVIEW,
    ReleaseStatus.PENDING_CONFIRM,
    ReleaseStatus.REVIEW_FAILED,
]


async def _build_task_list(
    db: AsyncSession, user: User, statuses: List[ReleaseStatus]
) -> List[MyTaskItem]:
    """Build list of releases where user has a role and status is in `statuses`."""

    # Join Release -> Version -> Project, and join users for names
    from app.models.project import Project, Version, Release

    stmt = (
        select(
            Release,
            Version,
            Project,
        )
        .select_from(Release)
        .join(Version, Release.version_id == Version.id)
        .join(Project, Version.project_id == Project.id)
        .where(Release.status.in_(statuses))
        .where(Project.is_active == True)
        .where(
            or_(
                Version.developer_id == user.id,
                Version.tester_id == user.id,
                Version.expert_id == user.id,
                Project.pm_user_id == user.id,
            )
        )
        .order_by(Release.updated_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Batch-load user names
    user_ids = set()
    for rel, ver, proj in rows:
        if ver.developer_id:
            user_ids.add(ver.developer_id)
        if ver.tester_id:
            user_ids.add(ver.tester_id)
        if ver.expert_id:
            user_ids.add(ver.expert_id)
        if proj.pm_user_id:
            user_ids.add(proj.pm_user_id)

    name_map = {}
    if user_ids:
        u_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in u_result.scalars().all():
            name_map[u.id] = u.full_name

    items = []
    for rel, ver, proj in rows:
        # Determine the user's role(s) on this release
        roles = []
        if proj.pm_user_id == user.id:
            roles.append("PM")
        if ver.developer_id == user.id:
            roles.append("开发")
        if ver.tester_id == user.id:
            roles.append("测试")
        if ver.expert_id == user.id:
            roles.append("专家")
        my_role = " / ".join(roles) if roles else None

        items.append(
            MyTaskItem(
                release_id=rel.id,
                project_id=proj.id,
                project_name=proj.name,
                version_id=ver.id,
                version_number=ver.version_number,
                release_number=rel.release_number,
                status=rel.status,
                change_notes=rel.change_notes,
                created_at=rel.created_at,
                updated_at=rel.updated_at,
                my_role=my_role,
                developer_name=name_map.get(ver.developer_id) if ver.developer_id else None,
                tester_name=name_map.get(ver.tester_id) if ver.tester_id else None,
                expert_name=name_map.get(ver.expert_id) if ver.expert_id else None,
                pm_name=name_map.get(proj.pm_user_id) if proj.pm_user_id else None,
            )
        )
    return items


@router.get("/todo", response_model=List[MyTaskItem])
async def get_my_todo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's pending tasks."""
    return await _build_task_list(db, current_user, TODO_STATUSES)


@router.get("/done", response_model=List[MyTaskItem])
async def get_my_done(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's completed tasks (released)."""
    return await _build_task_list(db, current_user, [ReleaseStatus.RELEASED])
