"""User management API routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.user import SystemRole, User
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.audit_service import create_audit_log
from app.services.user_service import (
    create_user,
    delete_user,
    get_user_by_id,
    get_users_paginated,
    update_user,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    org_unit_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.ADMIN, SystemRole.SUPER_ADMIN)),
):
    """Get a paginated list of users (ADMIN, SUPER_ADMIN only)."""
    users, total = await get_users_paginated(
        db=db,
        page=page,
        page_size=page_size,
        search=search,
        org_unit_id=org_unit_id,
    )
    return PaginatedResponse[UserResponse].create(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(
    user_create: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.ADMIN, SystemRole.SUPER_ADMIN)),
):
    """Create a new user (ADMIN, SUPER_ADMIN only)."""
    try:
        user = await create_user(db=db, user_create=user_create)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="create_user",
        resource_type="user",
        resource_id=str(user.id),
        details={"username": user.username, "email": user.email},
    )

    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get the current authenticated user's info."""
    return UserResponse.model_validate(current_user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single user by ID."""
    user = await get_user_by_id(db=db, user_id=user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user_endpoint(
    user_id: uuid.UUID,
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.ADMIN, SystemRole.SUPER_ADMIN)),
):
    """Update a user (ADMIN, SUPER_ADMIN only)."""
    try:
        user = await update_user(db=db, user_id=user_id, user_update=user_update)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="update_user",
        resource_type="user",
        resource_id=str(user.id),
        details=user_update.model_dump(exclude_unset=True, exclude={"password"}),
    )

    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.ADMIN, SystemRole.SUPER_ADMIN)),
):
    """Disable a user (soft delete) (ADMIN, SUPER_ADMIN only)."""
    success = await delete_user(db=db, user_id=user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="delete_user",
        resource_type="user",
        resource_id=str(user_id),
        details={"soft_delete": True},
    )
