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
    ProjectMember,
    ProjectRole,
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
    pm_name: Optional[str] = None


class MyTaskPage(BaseModel):
    """待办/已办分页响应(P1-10)。"""

    items: List[MyTaskItem]
    total: int
    page: int
    page_size: int


# 待办状态集合(功能7.1):
# - DRAFT: 开发上传代码包
# - CODE_PENDING_REVIEW / TEST_PENDING_REVIEW:
#   等待 LLM 评审完成(各角色等待)
# - PENDING_CONFIRM: PM 确认释放
# - REVIEW_FAILED: 评审失败,对应角色重新上传;PM 可特批放行
TODO_STATUSES = [
    ReleaseStatus.DRAFT,
    ReleaseStatus.CODE_PENDING_REVIEW,
    ReleaseStatus.TEST_PENDING_REVIEW,
    ReleaseStatus.PENDING_CONFIRM,
    ReleaseStatus.REVIEW_FAILED,
]


def _build_pm_user_filter(user: User):
    """构造 PM 用户匹配条件:pm_user_id 或项目成员表中的项目经理角色。

    修复: 之前只匹配 Project.pm_user_id(创建者),导致被分配为
    '项目经理'角色的成员看不到 PM 待办。
    """
    return or_(
        Project.pm_user_id == user.id,
        Project.id.in_(
            select(ProjectMember.project_id).where(
                ProjectMember.user_id == user.id,
                ProjectMember.project_role == ProjectRole.PROJECT_MANAGER,
            )
        ),
    )


def _build_role_status_filter(
    user: User,
    latest_failed_subq,
    statuses: List[ReleaseStatus],
):
    """构造角色↔状态严格匹配的过滤条件(功能7.1)。

    待办(TODO_STATUSES):
    - 开发: DRAFT(上传代码包), REVIEW_FAILED+CODE_REVIEW失败(重新上传代码包)
    - 测试: TEST_PENDING_REVIEW + test_report_path IS NULL(上传测试报告),
            REVIEW_FAILED+TEST_REPORT_REVIEW失败(重新上传测试报告)
    - PM:   CODE_PENDING_REVIEW(触发代码评审),
            TEST_PENDING_REVIEW + test_report_path IS NOT NULL(触发测试报告评审),
            PENDING_CONFIRM(确认释放),
            REVIEW_FAILED(特批放行,任意失败类型)

    已办(RELEASED/RELEASED_FORCED):
    - 开发/测试/PM: 所有已释放的版本(只要用户在该版本中有角色)
    """
    from app.models.review import ReviewType

    is_done = any(
        s in statuses
        for s in (ReleaseStatus.RELEASED, ReleaseStatus.RELEASED_FORCED)
    )

    if is_done:
        # 已办: 所有相关角色都能看到已释放的版本
        released_statuses = [
            s for s in statuses
            if s in (ReleaseStatus.RELEASED, ReleaseStatus.RELEASED_FORCED)
        ]
        developer_clause = and_(
            Version.developer_id == user.id,
            Release.status.in_(released_statuses),
        )
        tester_clause = and_(
            Version.tester_id == user.id,
            Release.status.in_(released_statuses),
        )
        pm_clause = and_(
            _build_pm_user_filter(user),
            Release.status.in_(released_statuses),
        )
        return or_(developer_clause, tester_clause, pm_clause)

    # 待办逻辑
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
    # 测试: 只在未上传测试报告时有待办(上传后待办传递给PM)
    tester_clause = and_(
        Version.tester_id == user.id,
        or_(
            and_(
                Release.status == ReleaseStatus.TEST_PENDING_REVIEW,
                Release.test_report_path.is_(None),
            ),
            and_(
                Release.status == ReleaseStatus.REVIEW_FAILED,
                latest_failed_subq.c.failed_review_type == ReviewType.TEST_REPORT_REVIEW,
            ),
        ),
    )
    # PM: 触发评审 + 确认释放 + 特批放行
    # 修复: 同时匹配 pm_user_id 和项目成员表中的项目经理角色
    pm_clause = and_(
        _build_pm_user_filter(user),
        or_(
            # 代码已上传,需要触发代码评审
            and_(
                Release.status == ReleaseStatus.CODE_PENDING_REVIEW,
                Release.code_package_path.is_not(None),
            ),
            # 测试报告已上传,需要触发测试报告评审
            and_(
                Release.status == ReleaseStatus.TEST_PENDING_REVIEW,
                Release.test_report_path.is_not(None),
            ),
            # 确认释放
            Release.status == ReleaseStatus.PENDING_CONFIRM,
            # 特批放行(任意失败类型)
            Release.status == ReleaseStatus.REVIEW_FAILED,
        ),
    )
    return or_(developer_clause, tester_clause, pm_clause)


def _build_todo_type(
    status: ReleaseStatus,
    role: str,
    failed_review_type: Optional[str],
    release: Optional[Release] = None,
) -> Optional[str]:
    """根据 status + role + 失败 review 类型生成中文待办文案(功能7.1)。"""
    from app.models.review import ReviewType

    if status == ReleaseStatus.DRAFT and role == "开发":
        return "上传代码包"
    if status == ReleaseStatus.CODE_PENDING_REVIEW and role == "PM":
        return "触发代码评审"
    if status == ReleaseStatus.TEST_PENDING_REVIEW:
        if role == "测试" and release and not release.test_report_path:
            return "上传测试报告"
        if role == "PM" and release and release.test_report_path:
            return "触发测试报告评审"
    if status == ReleaseStatus.PENDING_CONFIRM and role == "PM":
        return "确认释放"
    if status == ReleaseStatus.REVIEW_FAILED:
        if role == "PM":
            return "特批放行"
        if role == "开发" and failed_review_type == ReviewType.CODE_REVIEW:
            return "重新上传代码包"
        if role == "测试" and failed_review_type == ReviewType.TEST_REPORT_REVIEW:
            return "重新上传测试报告"
    return None


async def _build_task_list(
    db: AsyncSession,
    user: User,
    statuses: List[ReleaseStatus],
    offset: int = 0,
    limit: Optional[int] = None,
) -> tuple[List[MyTaskItem], int]:
    """Build list of releases where user has a role and status is in `statuses`.

    功能7.1:角色↔状态严格匹配过滤(已修复待办传递逻辑)
    - 开发只在 DRAFT / (REVIEW_FAILED + CODE_REVIEW) 看到待办
    - 测试只在 TEST_PENDING_REVIEW(未上传报告) / (REVIEW_FAILED + TEST_REPORT_REVIEW) 看到待办
    - PM 在 CODE_PENDING_REVIEW / TEST_PENDING_REVIEW(已上传报告) /
          PENDING_CONFIRM / REVIEW_FAILED 看到待办
    - 已办(RELEASED): 所有相关角色都能看到

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
        _build_role_status_filter(user, latest_failed_subq, statuses),
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
    # 加载 Project.members 以判断用户是否为项目经理角色成员
    from sqlalchemy.orm import selectinload
    stmt = (
        select(Release, Version, Project, latest_failed_subq.c.failed_review_type)
        .select_from(Release)
        .join(Version, Release.version_id == Version.id)
        .join(Project, Version.project_id == Project.id)
        .outerjoin(latest_failed_subq, sa_true())
        .options(selectinload(Project.members))
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
        # 修复: 被分配为"项目经理"角色的成员也算PM
        elif any(m.user_id == user.id and m.project_role == ProjectRole.PROJECT_MANAGER
                 for m in (proj.members or [])):
            roles.append("PM")
        if ver.developer_id == user.id:
            roles.append("开发")
        if ver.tester_id == user.id:
            roles.append("测试")
        my_role = " / ".join(roles) if roles else None

        # Generate todo_type per role (each role gets the one matching its status)
        # If user has multiple roles on this release, pick the first matching one.
        todo_type = None
        for role in roles:
            todo_type = _build_todo_type(rel.status, role, failed_type, rel)
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
