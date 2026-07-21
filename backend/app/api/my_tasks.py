"""My tasks API - todo and done lists for the current user."""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, and_, or_, func
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


class MyTaskPage(BaseModel):
    """待办/已办分页响应(P1-10)。"""

    items: List[MyTaskItem]
    total: int
    page: int
    page_size: int


TODO_STATUSES = [
    ReleaseStatus.CODE_PENDING_REVIEW,
    ReleaseStatus.TEST_PENDING_REVIEW,
    ReleaseStatus.EXPERT_PENDING_REVIEW,
    ReleaseStatus.PENDING_CONFIRM,
    ReleaseStatus.REVIEW_FAILED,
]


async def _build_task_list(
    db: AsyncSession,
    user: User,
    statuses: List[ReleaseStatus],
    offset: int = 0,
    limit: Optional[int] = None,
) -> tuple[List[MyTaskItem], int]:
    """Build list of releases where user has a role and status is in `statuses`.

    支持分页(P1-10):``offset`` / ``limit`` 控制分页范围,返回 ``(items, total)``。
    当 ``limit`` 为 ``None`` 时不限制返回条数(向后兼容)。
    """

    # Join Release -> Version -> Project, and join users for names
    from app.models.project import Project, Version, Release

    # 公共过滤条件
    base_filters = (
        Release.status.in_(statuses),
        Project.is_active == True,  # noqa: E712
        # 排除软删除版本(P1-11)
        Version.is_deleted == False,  # noqa: E712
        or_(
            Version.developer_id == user.id,
            Version.tester_id == user.id,
            Version.expert_id == user.id,
            Project.pm_user_id == user.id,
        ),
    )

    # 1) 统计总数(分页用)
    count_stmt = (
        select(func.count(func.distinct(Release.id)))
        .select_from(Release)
        .join(Version, Release.version_id == Version.id)
        .join(Project, Version.project_id == Project.id)
        .where(*base_filters)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    # 2) 主查询:按 Release.updated_at 倒序,应用分页
    stmt = (
        select(Release, Version, Project)
        .select_from(Release)
        .join(Version, Release.version_id == Version.id)
        .join(Project, Version.project_id == Project.id)
        .where(*base_filters)
        .order_by(Release.updated_at.desc())
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
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
    return items, total


@router.get("/todo", response_model=MyTaskPage)
async def get_my_todo(
    page: int = Query(1, ge=1, description="页码,从 1 开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数,1-100"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的待办(分页,P1-10)。

    返回 ``{ items, total, page, page_size }``。
    """
    offset = (page - 1) * page_size
    items, total = await _build_task_list(
        db, current_user, TODO_STATUSES, offset=offset, limit=page_size
    )
    return MyTaskPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/done", response_model=MyTaskPage)
async def get_my_done(
    page: int = Query(1, ge=1, description="页码,从 1 开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数,1-100"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的已办(已释放,分页,P1-10)。

    返回 ``{ items, total, page, page_size }``。
    """
    offset = (page - 1) * page_size
    items, total = await _build_task_list(
        db, current_user, [ReleaseStatus.RELEASED], offset=offset, limit=page_size
    )
    return MyTaskPage(items=items, total=total, page=page, page_size=page_size)
