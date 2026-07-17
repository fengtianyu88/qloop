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
    ProjectResponse,
    VersionCreate,
    VersionResponse,
)
from app.services.audit_service import create_audit_log
from app.services.permission_service import check_pm_permission, check_project_access
from app.services.project_service import (
    add_project_member,
    create_project,
    create_version,
    get_project_by_id,
    get_projects_for_user,
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
