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
    # 操作类型说明(功能7.1):根据角色+状态生成的中文待办文案
    todo_type: Optional[str] = None
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


# 待办状态集合(功能7.1):
# - DRAFT: 开发上传代码包
# - CODE_PENDING_REVIEW / TEST_PENDING_REVIEW / EXPERT_PENDING_REVIEW:
#   等待 LLM 评审完成(各角色等待)
# - PENDING_CONFIRM: PM 确认释放
# - REVIEW_FAILED: 评审失败,对应角色重新上传;PM 可特批放行
TODO_STATUSES = [
    ReleaseStatus.DRAFT,
    ReleaseStatus.CODE_PENDING_REVIEW,
    ReleaseStatus.TEST_PENDING_REVIEW,
    ReleaseStatus.EXPERT_PENDING_REVIEW,
    ReleaseStatus.PENDING_CONFIRM,
    ReleaseStatus.REVIEW_FAILED,
]


def _build_role_status_filter(
    user: User,
    latest_failed_subq,
):
    """构造角色↔状态严格匹配的过滤条件(功能7.1)。

    - 开发: DRAFT(上传代码包), REVIEW_FAILED + CODE_REVIEW 失败(重新上传代码包)
    - 测试: TEST_PENDING_REVIEW(上传测试报告),
            REVIEW_FAILED + TEST_REPORT_REVIEW 失败(重新上传测试报告)
    - 专家: EXPERT_PENDING_REVIEW(上传评审报告),
            REVIEW_FAILED + EXPERT_REPORT_REVIEW 失败(重新上传评审报告)
    - PM:   PENDING_CONFIRM(确认释放), REVIEW_FAILED(特批放行,任意失败类型)
    """
    from app.models.review import ReviewType

    developer_clause = and_(
        Version.developer_id == user.id,
        or_(
            Release.status == ReleaseStatus.DRAFT,
            and_(
                Release.status == ReleaseStatus.REVIEW_FAILED,
                latest_failed_subq.c.failed_review_type == ReviewType.CODE_REVIEW,
            ),
        ),
    )
    tester_clause = and_(
        Version.tester_id == user.id,
        or_(
            Release.status == ReleaseStatus.TEST_PENDING_REVIEW,
            and_(
                Release.status == ReleaseStatus.REVIEW_FAILED,
                latest_failed_subq.c.failed_review_type == ReviewType.TEST_REPORT_REVIEW,
            ),
        ),
    )
    expert_clause = and_(
        Version.expert_id == user.id,
        or_(
            Release.status == ReleaseStatus.EXPERT_PENDING_REVIEW,
            and_(
                Release.status == ReleaseStatus.REVIEW_FAILED,
                latest_failed_subq.c.failed_review_type == ReviewType.EXPERT_REPORT_REVIEW,
            ),
        ),
    )
    pm_clause = and_(
        Project.pm_user_id == user.id,
        or_(
            Release.status == ReleaseStatus.PENDING_CONFIRM,
            Release.status == ReleaseStatus.REVIEW_FAILED,
        ),
    )
    return or_(developer_clause, tester_clause, expert_clause, pm_clause)


def _build_todo_type(
    status: ReleaseStatus,
    role: str,
    failed_review_type: Optional[str],
) -> Optional[str]:
    """根据 status + role + 失败 review 类型生成中文待办文案(功能7.1)。"""
    from app.models.review import ReviewType

    if status == ReleaseStatus.DRAFT and role == "开发":
        return "上传代码包"
    if status == ReleaseStatus.TEST_PENDING_REVIEW and role == "测试":
        return "上传测试报告"
    if status == ReleaseStatus.EXPERT_PENDING_REVIEW and role == "专家":
        return "上传评审报告"
    if status == ReleaseStatus.PENDING_CONFIRM and role == "PM":
        return "确认释放"
    if status == ReleaseStatus.REVIEW_FAILED:
        if role == "PM":
            return "特批放行"
        if role == "开发" and failed_review_type == ReviewType.CODE_REVIEW:
            return "重新上传代码包"
        if role == "测试" and failed_review_type == ReviewType.TEST_REPORT_REVIEW:
            return "重新上传测试报告"
        if role == "专家" and failed_review_type == ReviewType.EXPERT_REPORT_REVIEW:
            return "重新上传评审报告"
    return None


async def _build_task_list(
    db: AsyncSession,
    user: User,
    statuses: List[ReleaseStatus],
    offset: int = 0,
    limit: Optional[int] = None,
) -> tuple[List[MyTaskItem], int]:
    """Build list of releases where user has a role and status is in `statuses`.

    功能7.1:角色↔状态严格匹配过滤
    - 开发只在 DRAFT / (REVIEW_FAILED + CODE_REVIEW) 看到待办
    - 测试只在 TEST_PENDING_REVIEW / (REVIEW_FAILED + TEST_REPORT_REVIEW) 看到待办
    - 专家只在 EXPERT_PENDING_REVIEW / (REVIEW_FAILED + EXPERT_REPORT_REVIEW) 看到待办
    - PM 只在 PENDING_CONFIRM / REVIEW_FAILED 看到待办

    支持分页(P1-10):``offset`` / ``limit`` 控制分页范围,返回 ``(items, total)``。
    当 ``limit`` 为 ``None`` 时不限制返回条数(向后兼容)。
    """
    from app.models.project import Project, Version, Release
    from app.models.review import LLMReview, ReviewResult
    from sqlalchemy import true as sa_true

    # LATERAL 子查询:每个 release 最近一次失败的 review_type(用于 REVIEW_FAILED 时判断角色)
    latest_failed_subq = (
        select(LLMReview.review_type.label("failed_review_type"))
        .where(
            LLMReview.release_id == Release.id,
            LLMReview.result.in_([ReviewResult.FAILED, ReviewResult.ERROR]),
        )
        .order_by(LLMReview.created_at.desc())
        .limit(1)
        .lateral("latest_failed")
    )

    # 公共过滤条件
    base_filters = (
        Project.is_active == True,  # noqa: E712
        Version.is_deleted == False,  # noqa: E712
        _build_role_status_filter(user, latest_failed_subq),
    )

    # 1) 统计总数(分页用)
    count_stmt = (
        select(func.count(func.distinct(Release.id)))
        .select_from(Release)
        .join(Version, Release.version_id == Version.id)
        .join(Project, Version.project_id == Project.id)
        .outerjoin(latest_failed_subq, sa_true())
        .where(*base_filters)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    # 2) 主查询:按 Release.updated_at 倒序,应用分页
    stmt = (
        select(Release, Version, Project, latest_failed_subq.c.failed_review_type)
        .select_from(Release)
        .join(Version, Release.version_id == Version.id)
        .join(Project, Version.project_id == Project.id)
        .outerjoin(latest_failed_subq, sa_true())
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
    for rel, ver, proj, _failed_type in rows:
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
    for rel, ver, proj, failed_type in rows:
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

        # Generate todo_type per role (each role gets the one matching its status)
        # If user has multiple roles on this release, pick the first matching one.
        todo_type = None
        for role in roles:
            todo_type = _build_todo_type(rel.status, role, failed_type)
            if todo_type is not None:
                break

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
                todo_type=todo_type,
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
