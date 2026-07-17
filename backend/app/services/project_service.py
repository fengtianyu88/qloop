"""Project management service."""

import uuid
from typing import List, Optional

from sqlalchemy import select
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
from app.schemas.project import ProjectCreate, ProjectMemberCreate, VersionCreate


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
    await db.refresh(project)
    return project


async def get_project_by_id(
    db: AsyncSession, project_id: uuid.UUID
) -> Optional[Project]:
    """Get a project by ID with members eagerly loaded."""
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.members))
        .where(Project.id == project_id)
    )
    return result.scalar_one_or_none()


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
    return list(result.scalars().all())


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
