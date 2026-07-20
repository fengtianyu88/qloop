"""Project management API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.user import SystemRole, User
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberUpdate,
    ProjectResponse,
    VersionCreate,
    VersionResponse,
)
from app.services.audit_service import create_audit_log
from app.services.permission_service import check_pm_permission, check_project_access
from app.services.project_service import (
    delete_version,
    list_versions_with_release_status,
    add_project_member,
    create_project,
    create_version,
    delete_project_member,
    get_project_by_id,
    get_projects_for_user,
    update_project_member,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all projects the current user participates in."""
    projects = await get_projects_for_user(db=db, user_id=current_user.id)
    return [ProjectResponse.model_validate(p) for p in projects]


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_endpoint(
    project_create: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(SystemRole.DEVELOPER, SystemRole.ADMIN, SystemRole.SUPER_ADMIN)
    ),
):
    """Create a new project (DEVELOPER, ADMIN, SUPER_ADMIN only)."""
    project = await create_project(
        db=db, project_create=project_create, pm_user_id=current_user.id
    )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="create_project",
        resource_type="project",
        resource_id=str(project.id),
        details={"name": project.name},
    )

    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a project by ID."""
    project = await get_project_by_id(db=db, project_id=project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Check access permission
    has_access = await check_project_access(db, current_user, project_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this project",
        )

    return ProjectResponse.model_validate(project)


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    project_id: uuid.UUID,
    member_create: ProjectMemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a member to a project (PM only)."""
    # Check PM permission
    is_pm = await check_pm_permission(db, current_user, project_id)
    if not is_pm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project manager can add members",
        )

    # Verify project exists
    project = await get_project_by_id(db=db, project_id=project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    try:
        member = await add_project_member(
            db=db, project_id=project_id, member_create=member_create
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="add_project_member",
        resource_type="project_member",
        resource_id=str(member.id),
        details={
            "project_id": str(project_id),
            "user_id": str(member_create.user_id),
            "role": member_create.project_role.value,
        },
    )

    return ProjectMemberResponse.model_validate(member)


@router.patch(
    "/{project_id}/members/{member_id}",
    response_model=ProjectMemberResponse,
)
async def update_member(
    project_id: uuid.UUID,
    member_id: uuid.UUID,
    member_update: ProjectMemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a project member's role.

    Permission rules:
    - super_admin / admin: can update any member, including the PM row.
    - Project manager (PM): can update any member EXCEPT the PM row.
    """
    # Caller must be PM or admin
    is_pm = await check_pm_permission(db, current_user, project_id)
    if not is_pm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project manager or an admin can update members",
        )

    # Verify project exists and fetch pm_user_id
    project = await get_project_by_id(db=db, project_id=project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Fetch the target member
    from sqlalchemy import select
    from app.models.project import ProjectMember
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project member not found",
        )

    # PM cannot modify the PM row; only admin/super_admin can.
    is_admin = current_user.system_role in (
        "admin",
        "super_admin",
    ) or getattr(current_user.system_role, "value", None) in (
        "admin",
        "super_admin",
    )
    if member.user_id == project.pm_user_id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project manager cannot modify the PM row; only an admin can",
        )

    try:
        updated = await update_project_member(
            db=db, member_id=member_id, member_update=member_update
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="update_project_member",
        resource_type="project_member",
        resource_id=str(updated.id),
        details={
            "project_id": str(project_id),
            "user_id": str(updated.user_id),
            "new_role": member_update.project_role.value
            if hasattr(member_update.project_role, "value")
            else str(member_update.project_role),
        },
    )

    return ProjectMemberResponse.model_validate(updated)


@router.delete(
    "/{project_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    project_id: uuid.UUID,
    member_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a project member.

    Permission rules:
    - super_admin / admin: can remove any member, including the PM row.
    - Project manager (PM): can remove any member EXCEPT the PM row.
    """
    # Caller must be PM or admin
    is_pm = await check_pm_permission(db, current_user, project_id)
    if not is_pm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project manager or an admin can remove members",
        )

    # Verify project exists
    project = await get_project_by_id(db=db, project_id=project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Fetch the target member
    from sqlalchemy import select
    from app.models.project import ProjectMember
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project member not found",
        )

    # PM cannot remove the PM row; only admin/super_admin can.
    is_admin = current_user.system_role in (
        "admin",
        "super_admin",
    ) or getattr(current_user.system_role, "value", None) in (
        "admin",
        "super_admin",
    )
    if member.user_id == project.pm_user_id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project manager cannot remove the PM row; only an admin can",
        )

    deleted = await delete_project_member(db=db, member_id=member_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project member not found",
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="remove_project_member",
        resource_type="project_member",
        resource_id=str(member_id),
        details={
            "project_id": str(project_id),
            "removed_user_id": str(member.user_id),
        },
    )

    return None


@router.post(
    "/{project_id}/versions",
    response_model=VersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version_endpoint(
    project_id: uuid.UUID,
    version_create: VersionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new version in a project (PM only)."""
    # Check PM permission
    is_pm = await check_pm_permission(db, current_user, project_id)
    if not is_pm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project manager can create versions",
        )

    # Verify project exists
    project = await get_project_by_id(db=db, project_id=project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    try:
        version = await create_version(
            db=db, project_id=project_id, version_create=version_create
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="create_version",
        resource_type="version",
        resource_id=str(version.id),
        details={
            "project_id": str(project_id),
            "version_number": version.version_number,
        },
    )

    return VersionResponse.model_validate(version)


@router.delete(
    "/{project_id}/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_version_endpoint(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a version (PM only). Refuses if any release is already released."""
    is_pm = await check_pm_permission(db, current_user, project_id)
    if not is_pm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project manager (or admin) can delete versions",
        )

    try:
        deleted = await delete_version(db=db, version_id=version_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="delete_version",
        resource_type="version",
        resource_id=str(version_id),
        details={"project_id": str(project_id)},
    )
    return None


@router.get("/{project_id}/versions")
async def list_project_versions(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all versions of a project with latest release status.

    Used by the frontend to render the version list and decide whether
    each version can be deleted (released versions cannot).
    """
    project = await get_project_by_id(db=db, project_id=project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    items = await list_versions_with_release_status(db=db, project_id=project_id)
    # Convert enum to string for JSON serialization
    for it in items:
        if it.get("latest_release_status") is not None:
            it["latest_release_status"] = it["latest_release_status"].value
    return items

