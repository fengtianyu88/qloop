"""Permission checking service."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectMember
from app.models.user import SystemRole, User


async def check_project_access(
    db: AsyncSession, user: User, project_id: uuid.UUID
) -> bool:
    """Check whether a user has access to a project.

    A user has access if they are the PM, a project member, or an admin/super_admin.

    Args:
        db: The async database session.
        user: The user to check.
        project_id: The project ID.

    Returns:
        True if the user has access, False otherwise.
    """
    # Admins and super admins have access to all projects
    if user.system_role in (SystemRole.ADMIN, SystemRole.SUPER_ADMIN):
        return True

    # Check if user is the PM
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.pm_user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is not None:
        return True

    # Check if user is a project member
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is not None:
        return True

    return False


async def check_pm_permission(
    db: AsyncSession, user: User, project_id: uuid.UUID
) -> bool:
    """Check whether a user is the PM of a project (or an admin/super_admin).

    Args:
        db: The async database session.
        user: The user to check.
        project_id: The project ID.

    Returns:
        True if the user is the PM or an admin/super_admin, False otherwise.
    """
    # Admins and super admins have PM-level access
    if user.system_role in (SystemRole.ADMIN, SystemRole.SUPER_ADMIN):
        return True

    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.pm_user_id == user.id,
        )
    )
    return result.scalar_one_or_none() is not None
