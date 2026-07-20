"""Project management service."""

import uuid
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import (
    Project,
    ProjectMember,
    ProjectRole,
    Release,
    ReleaseStatus,
    Version,
)
from app.schemas.project import ProjectCreate, ProjectMemberCreate, ProjectMemberUpdate, VersionCreate


async def create_project(
    db: AsyncSession, project_create: ProjectCreate, pm_user_id: uuid.UUID
) -> Project:
    """Create a new project and add the PM as a member.

    Args:
        db: The async database session.
        project_create: The project creation data.
        pm_user_id: The ID of the project manager.

    Returns:
        The created Project object.
    """
    project = Project(
        name=project_create.name,
        description=project_create.description,
        pm_user_id=pm_user_id,
        is_active=True,
    )
    db.add(project)
    await db.flush()

    # Add the PM as a project member with PROJECT_MANAGER role
    member = ProjectMember(
        project_id=project.id,
        user_id=pm_user_id,
        project_role=ProjectRole.PROJECT_MANAGER,
    )
    db.add(member)
    await db.commit()
    # Re-fetch with members eagerly loaded to avoid async lazy-load errors
    # when serializing the response (ProjectResponse includes members).
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.members))
        .where(Project.id == project.id)
    )
    return result.scalar_one()


async def get_project_by_id(
    db: AsyncSession, project_id: uuid.UUID
) -> Optional[Project]:
    """Get a project by ID with members eagerly loaded."""
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.members))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is not None:
        await _enrich_projects(db, [project])
    return project


async def get_projects_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> List[Project]:
    """Get all projects where the user is PM or a member.

    Args:
        db: The async database session.
        user_id: The user ID.

    Returns:
        A list of Project objects.
    """
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.members))
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user_id)
        .where(Project.is_active == True)  # noqa: E712
        .distinct()
        .order_by(Project.created_at.desc())
    )
    projects = list(result.scalars().all())
    # Populate pm_name + latest_activity_at for the response.
    await _enrich_projects(db, projects)
    return projects


async def add_project_member(
    db: AsyncSession,
    project_id: uuid.UUID,
    member_create: ProjectMemberCreate,
) -> ProjectMember:
    """Add a member to a project.

    Args:
        db: The async database session.
        project_id: The project ID.
        member_create: The member creation data.

    Returns:
        The created ProjectMember object.

    Raises:
        ValueError: If the member already exists in the project.
    """
    # Check if already a member
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == member_create.user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("User is already a member of this project")

    member = ProjectMember(
        project_id=project_id,
        user_id=member_create.user_id,
        project_role=member_create.project_role,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def update_project_member(
    db: AsyncSession,
    member_id: uuid.UUID,
    member_update: ProjectMemberUpdate,
) -> ProjectMember:
    """Update a project member's role.

    Args:
        db: The async database session.
        member_id: The project member ID.
        member_update: The update payload.

    Returns:
        The updated ProjectMember object.

    Raises:
        ValueError: If the member does not exist.
    """
    result = await db.execute(
        select(ProjectMember).where(ProjectMember.id == member_id)
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise ValueError("Project member not found")

    member.project_role = member_update.project_role
    await db.commit()
    await db.refresh(member)
    return member


async def delete_project_member(
    db: AsyncSession,
    member_id: uuid.UUID,
) -> bool:
    """Delete a project member.

    Args:
        db: The async database session.
        member_id: The project member ID.

    Returns:
        True if deleted, False if not found.
    """
    result = await db.execute(
        select(ProjectMember).where(ProjectMember.id == member_id)
    )
    member = result.scalar_one_or_none()
    if member is None:
        return False

    await db.delete(member)
    await db.commit()
    return True


async def create_version(
    db: AsyncSession,
    project_id: uuid.UUID,
    version_create: VersionCreate,
) -> Version:
    """Create a new version and its first draft release.

    Args:
        db: The async database session.
        project_id: The project ID.
        version_create: The version creation data.

    Returns:
        The created Version object.

    Raises:
        ValueError: If the version_number already exists in the project.
    """
    # Check for duplicate version_number within the project
    existing = await db.execute(
        select(Version).where(
            Version.project_id == project_id,
            Version.version_number == version_create.version_number,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(
            f"Version number '{version_create.version_number}' "
            f"already exists in this project"
        )

    version = Version(
        project_id=project_id,
        version_number=version_create.version_number,
        description=version_create.description,
        developer_id=version_create.developer_id,
        tester_id=version_create.tester_id,
        expert_id=version_create.expert_id,
    )
    db.add(version)
    await db.flush()

    # Create the first draft release
    release = Release(
        version_id=version.id,
        release_number=1,
        status=ReleaseStatus.DRAFT,
    )
    db.add(release)
    await db.commit()
    await db.refresh(version)
    return version


async def get_version_by_id(
    db: AsyncSession, version_id: uuid.UUID
) -> Optional[Version]:
    """Get a version by ID with releases eagerly loaded."""
    result = await db.execute(
        select(Version)
        .options(selectinload(Version.releases))
        .where(Version.id == version_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Enrichment helpers (pm_name + latest_activity_at)
# ---------------------------------------------------------------------------
async def _enrich_projects(db: AsyncSession, projects: List[Project]) -> None:
    """Populate ``pm_name`` and ``latest_activity_at`` on each Project.

    Mutates the projects in place. The extra attributes are stored
    directly on the instance ``__dict__`` so SQLAlchemy's mapper does
    not intercept or refresh them, and Pydantic's ``from_attributes``
    will pick them up when ``ProjectResponse.model_validate(p)`` runs.
    """
    if not projects:
        return

    from sqlalchemy.orm import make_transient
    from app.models.user import User
    from app.models.project import Release, Version

    pm_ids = {p.pm_user_id for p in projects}
    if pm_ids:
        res = await db.execute(
            select(User.id, User.full_name).where(User.id.in_(pm_ids))
        )
        name_map = {row.id: row.full_name for row in res.all()}
    else:
        name_map = {}

    # latest_activity_at = MAX(releases.updated_at) per project
    project_ids = [p.id for p in projects]
    if project_ids:
        res = await db.execute(
            select(
                Version.project_id.label("project_id"),
                func.max(Release.updated_at).label("latest"),
            )
            .select_from(Release)
            .join(Version, Release.version_id == Version.id)
            .where(Version.project_id.in_(project_ids))
            .group_by(Version.project_id)
        )
        latest_map = {row.project_id: row.latest for row in res.all()}
    else:
        latest_map = {}

    # Detach from the session so SA never tries to lazy-load or refresh
    # the transient attributes we are about to set.
    for p in projects:
        make_transient(p)
        # Walk the already-loaded relationships so they stay accessible.
    for p in projects:
        # Use object.__setattr__ to bypass SQLAlchemy attribute events.
        object.__setattr__(p, "pm_name", name_map.get(p.pm_user_id))
        object.__setattr__(p, "latest_activity_at", latest_map.get(p.id))


async def delete_version(
    db: AsyncSession,
    version_id: uuid.UUID,
    allow_released: bool = False,
) -> bool:
    """Delete a version and cascade-delete its releases/external_recipients.

    Args:
        db: The async database session.
        version_id: The version ID to delete.
        allow_released: If True, bypass the released-release check
            (used when super_admin forces deletion). Defaults to False.

    Returns:
        True if deleted, False if not found.
    Raises:
        ValueError: if a release is already released and allow_released=False.
    """
    from app.models.project import Release, ReleaseStatus
    result = await db.execute(select(Version).where(Version.id == version_id))
    version = result.scalar_one_or_none()
    if version is None:
        return False

    if not allow_released:
        # Check if any release is already RELEASED
        rel_result = await db.execute(
            select(Release)
            .where(Release.version_id == version_id)
            .where(Release.status == ReleaseStatus.RELEASED)
        )
        released_releases = rel_result.scalars().all()
        if released_releases:
            raise ValueError(
                f"Cannot delete version {version.version_number}: "
                f"{len(released_releases)} release(s) already released"
            )

    await db.delete(version)
    await db.commit()
    return True


async def list_versions_with_release_status(
    db: AsyncSession, project_id: uuid.UUID
) -> List[dict]:
    """List all versions of a project with the latest release status.

    Returns a list of plain dicts (not Version ORM instances) so we can
    attach an extra `latest_release_status` field without messing with
    the ORM mapper.
    """
    from app.models.project import Release, ReleaseStatus, Version

    stmt = (
        select(Version, Release.status)
        .select_from(Version)
        .outerjoin(Release, Release.version_id == Version.id)
        .where(Version.project_id == project_id)
        .order_by(Version.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Aggregate: for each version, keep the "highest" status if multiple
    # releases exist (released > review_failed > pending_confirm > *_pending_review > draft)
    by_id: dict = {}
    priority = {
        ReleaseStatus.RELEASED: 6,
        ReleaseStatus.REVIEW_FAILED: 5,
        ReleaseStatus.PENDING_CONFIRM: 4,
        ReleaseStatus.EXPERT_PENDING_REVIEW: 3,
        ReleaseStatus.TEST_PENDING_REVIEW: 2,
        ReleaseStatus.CODE_PENDING_REVIEW: 1,
        ReleaseStatus.DRAFT: 0,
    }
    for ver, rel_status in rows:
        if ver.id not in by_id:
            by_id[ver.id] = {
                "id": ver.id,
                "version_number": ver.version_number,
                "description": ver.description,
                "developer_id": ver.developer_id,
                "tester_id": ver.tester_id,
                "expert_id": ver.expert_id,
                "project_id": ver.project_id,
                "created_at": ver.created_at,
                "updated_at": ver.updated_at,
                "latest_release_status": None,
            }
        if rel_status is not None:
            cur = by_id[ver.id]["latest_release_status"]
            if cur is None or priority.get(rel_status, 0) > priority.get(cur, 0):
                by_id[ver.id]["latest_release_status"] = rel_status

    return list(by_id.values())

