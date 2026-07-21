"""Permission checking service."""

import uuid

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectMember, Version
from app.models.user import SystemRole, User


async def check_project_access(
    db: AsyncSession, user: User, project_id: uuid.UUID
) -> bool:
    """Check whether a user has access to a project.

    A user has access if they are:
    - an admin/super_admin, OR
    - the PM of the project, OR
    - a ProjectMember of the project, OR
    - **assigned as developer/tester/expert on any version of the project**
      (兜底: PM 创建版本时虽然指定了 developer_id/tester_id/expert_id,
      但历史数据可能未自动加入 ProjectMember 表,这里补齐权限)

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

    # 兜底: 检查是否被分配为该项目任一版本的 developer/tester/expert
    # (历史数据兼容: 早期 create_version 未自动加入 ProjectMember)
    result = await db.execute(
        select(Version).where(
            Version.project_id == project_id,
            Version.is_deleted == False,  # noqa: E712
            or_(
                Version.developer_id == user.id,
                Version.tester_id == user.id,
                Version.expert_id == user.id,
            ),
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
