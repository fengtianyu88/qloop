"""Search API routes for releases and projects."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import Project, Release, ReleaseStatus, Version
from app.models.user import SystemRole, User
from app.schemas.common import PaginatedResponse
from app.schemas.project import ProjectResponse, ReleaseListResponse

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/releases", response_model=PaginatedResponse[ReleaseListResponse])
async def search_releases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    developer_name: Optional[str] = Query(None),
    project_name: Optional[str] = Query(None),
    version_number: Optional[str] = Query(None),
    change_notes: Optional[str] = Query(None),
    status: Optional[ReleaseStatus] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search releases with optional filters.

    Guests can only see releases with ``RELEASED`` status.

    Filters:
        - developer_name: Partial match on developer's full name.
        - project_name: Partial match on project name.
        - version_number: Partial match on version number.
        - change_notes: Partial match on change notes.
        - status: Exact match on release status.
    """
    # Aliased User models for developer, tester, expert joins
    DeveloperUser = aliased(User)
    TesterUser = aliased(User)
    ExpertUser = aliased(User)

    # Build the filter conditions
    conditions = []

    # Guests can only see released releases
    if current_user.system_role == SystemRole.GUEST:
        conditions.append(Release.status == ReleaseStatus.RELEASED)
    elif status is not None:
        conditions.append(Release.status == status)

    # 排除软删除版本(P1-11):已归档的版本及其 releases 不出现在搜索结果中
    conditions.append(Version.is_deleted == False)  # noqa: E712

    if developer_name:
        conditions.append(
            DeveloperUser.full_name.ilike(f"%{developer_name}%")
        )

    if project_name:
        conditions.append(Project.name.ilike(f"%{project_name}%"))

    if version_number:
        conditions.append(Version.version_number.ilike(f"%{version_number}%"))

    if change_notes:
        conditions.append(Release.change_notes.ilike(f"%{change_notes}%"))

    # Build the data query
    data_query = (
        select(
            Release.id,
            Release.version_id,
            Release.release_number,
            Release.status,
            Release.change_notes,
            Release.code_package_path,
            Release.test_report_path,
            Release.review_report_path,
            Release.download_link,
            Release.link_expiry,
            Release.confirmed_by,
            Release.confirmed_at,
            Release.created_at,
            Release.updated_at,
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            Version.version_number.label("version_number"),
            Version.developer_id.label("developer_id"),
            DeveloperUser.full_name.label("developer_name"),
            Version.tester_id.label("tester_id"),
            TesterUser.full_name.label("tester_name"),
            Version.expert_id.label("expert_id"),
            ExpertUser.full_name.label("expert_name"),
        )
        .select_from(Release)
        .join(Version, Release.version_id == Version.id)
        .join(Project, Version.project_id == Project.id)
        .outerjoin(DeveloperUser, Version.developer_id == DeveloperUser.id)
        .outerjoin(TesterUser, Version.tester_id == TesterUser.id)
        .outerjoin(ExpertUser, Version.expert_id == ExpertUser.id)
    )

    if conditions:
        data_query = data_query.where(*conditions)

    # Count total
    count_subquery = (
        select(Release.id)
        .select_from(Release)
        .join(Version, Release.version_id == Version.id)
        .join(Project, Version.project_id == Project.id)
        .outerjoin(DeveloperUser, Version.developer_id == DeveloperUser.id)
        .outerjoin(TesterUser, Version.tester_id == TesterUser.id)
        .outerjoin(ExpertUser, Version.expert_id == ExpertUser.id)
    )
    if conditions:
        count_subquery = count_subquery.where(*conditions)

    count_query = select(func.count()).select_from(count_subquery.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    data_query = (
        data_query.offset(offset)
        .limit(page_size)
        .order_by(Release.created_at.desc())
    )

    result = await db.execute(data_query)
    rows = result.all()

    items = [
        ReleaseListResponse(
            id=row.id,
            version_id=row.version_id,
            release_number=row.release_number,
            status=row.status,
            change_notes=row.change_notes,
            code_package_path=row.code_package_path,
            test_report_path=row.test_report_path,
            review_report_path=row.review_report_path,
            download_link=row.download_link,
            link_expiry=row.link_expiry,
            confirmed_by=row.confirmed_by,
            confirmed_at=row.confirmed_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            project_id=row.project_id,
            project_name=row.project_name,
            version_number=row.version_number,
            developer_id=row.developer_id,
            developer_name=row.developer_name,
            tester_id=row.tester_id,
            tester_name=row.tester_name,
            expert_id=row.expert_id,
            expert_name=row.expert_name,
        )
        for row in rows
    ]

    return PaginatedResponse[ReleaseListResponse].create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/projects", response_model=PaginatedResponse[ProjectResponse])
async def search_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search projects by name.

    Guests can only see projects that have at least one released release.
    """
    query = select(Project).options(selectinload(Project.members)).where(Project.is_active == True)  # noqa: E712

    if name:
        query = query.where(Project.name.ilike(f"%{name}%"))

    # Guests can only see projects with at least one released release
    if current_user.system_role == SystemRole.GUEST:
        released_exists = (
            select(Release.id)
            .join(Version, Release.version_id == Version.id)
            .where(Version.project_id == Project.id)
            .where(Release.status == ReleaseStatus.RELEASED)
            .exists()
        )
        query = query.where(released_exists)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = (
        query.offset(offset)
        .limit(page_size)
        .order_by(Project.created_at.desc())
    )

    result = await db.execute(query)
    projects = list(result.scalars().all())

    # Populate pm_name + latest_activity_at for the response.
    from app.services.project_service import _enrich_projects
    await _enrich_projects(db, projects)

    return PaginatedResponse[ProjectResponse].create(
        items=[ProjectResponse.model_validate(p) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Export everything the current user can access (CSV)
# ---------------------------------------------------------------------------
@router.get("/export")
async def export_all(
    format: str = Query("csv", regex="^(csv)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export **all** releases and projects the current user can access.

    Returns a CSV file with two sheets worth of data (releases + projects)
    concatenated in a single document with a ``record_type`` column to
    tell them apart.
    """
    import csv
    import io
    from fastapi.responses import StreamingResponse

    # --- Releases (all rows matching user's access; same logic as search_releases) ---
    DeveloperUser = aliased(User)
    TesterUser = aliased(User)
    ExpertUser = aliased(User)

    rel_query = (
        select(
            Release.id,
            Release.release_number,
            Release.status,
            Release.change_notes,
            Release.created_at,
            Release.updated_at,
            Project.name.label("project_name"),
            Version.version_number.label("version_number"),
            DeveloperUser.full_name.label("developer_name"),
            TesterUser.full_name.label("tester_name"),
            ExpertUser.full_name.label("expert_name"),
        )
        .select_from(Release)
        .join(Version, Release.version_id == Version.id)
        .join(Project, Version.project_id == Project.id)
        .outerjoin(DeveloperUser, Version.developer_id == DeveloperUser.id)
        .outerjoin(TesterUser, Version.tester_id == TesterUser.id)
        .outerjoin(ExpertUser, Version.expert_id == ExpertUser.id)
        # 排除软删除版本(P1-11)
        .where(Version.is_deleted == False)  # noqa: E712
    )
    if current_user.system_role == SystemRole.GUEST:
        rel_query = rel_query.where(Release.status == ReleaseStatus.RELEASED)
    rel_query = rel_query.order_by(Release.created_at.desc())
    rel_result = await db.execute(rel_query)
    rel_rows = rel_result.all()

    # --- Projects (all rows the user can access) ---
    from app.services.project_service import _enrich_projects, get_projects_for_user
    projects = await get_projects_for_user(db=db, user_id=current_user.id)
    await _enrich_projects(db, projects)

    # --- Build CSV ---
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "record_type", "id", "project_name", "version_number",
        "release_number", "status", "change_notes",
        "developer_name", "tester_name", "expert_name",
        "pm_name", "created_at", "updated_at", "latest_activity_at",
    ])
    for r in rel_rows:
        writer.writerow([
            "release",
            str(r.id),
            r.project_name or "",
            r.version_number or "",
            r.release_number,
            r.status.value if hasattr(r.status, "value") else str(r.status),
            r.change_notes or "",
            r.developer_name or "",
            r.tester_name or "",
            r.expert_name or "",
            "",  # pm_name N/A for releases
            r.created_at.isoformat() if r.created_at else "",
            r.updated_at.isoformat() if r.updated_at else "",
            "",  # latest_activity_at N/A for releases
        ])
    for p in projects:
        writer.writerow([
            "project",
            str(p.id),
            p.name,
            "",  # version_number N/A
            "",  # release_number N/A
            "active" if p.is_active else "inactive",
            p.description or "",
            "", "", "",  # developer/tester/expert N/A
            getattr(p, "pm_name", "") or "",
            p.created_at.isoformat() if p.created_at else "",
            p.updated_at.isoformat() if p.updated_at else "",
            getattr(p, "latest_activity_at", None).isoformat()
                if getattr(p, "latest_activity_at", None) else "",
        ])

    buf.seek(0)
    filename = f"qloop_export_{current_user.username}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
