"""User management API routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.user import SystemRole, User
from app.schemas.common import PaginatedResponse
from app.schemas.user import (
    ChangePasswordRequest,
    UserCreate,
    UserGitCredentialsRequest,
    UserResponse,
    UserUpdate,
)
from app.utils.security import hash_password, verify_password
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
    page_size: int = Query(20, ge=1, le=500),
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


@router.put("/me/password")
async def change_my_password(
    request: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """让已登录用户修改自己的密码(无需管理员权限)。

    需要 current_password 验证身份,new_password 经强度校验后写入。
    """
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码不正确",
        )
    if request.current_password == request.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与当前密码相同",
        )
    current_user.hashed_password = hash_password(request.new_password)
    await db.commit()

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="change_own_password",
        resource_type="user",
        resource_id=str(current_user.id),
        details={},
    )
    return {"message": "密码修改成功"}


@router.put("/me/git")
async def update_my_git_credentials(
    request: UserGitCredentialsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """让已登录用户设置/更新自己的 Git 推送凭据(git_username / git_token)。

    用于版本释放后,以当前用户(通常是项目经理)的 Git 账号推送到项目 Git 仓库。
    传入空字符串会清除对应字段。
    """
    changed: dict = {}
    if request.git_username is not None:
        new_name = request.git_username.strip() or None
        if current_user.git_username != new_name:
            current_user.git_username = new_name
            changed["git_username"] = bool(new_name)
    if request.git_token is not None:
        # 空字符串表示清除 token
        new_token = request.git_token.strip() or None
        # 出于安全考虑,不记录 token 原文,仅记录是否变更
        if bool(new_token) != bool(current_user.git_token):
            current_user.git_token = new_token
            changed["git_token"] = bool(new_token)

    if changed:
        await db.commit()
        await create_audit_log(
            db=db,
            user_id=current_user.id,
            action="update_own_git_credentials",
            resource_type="user",
            resource_id=str(current_user.id),
            details={"changed_fields": list(changed.keys())},
        )

    return {
        "message": "Git 凭据已更新" if changed else "Git 凭据未变更",
        "has_git_token": bool(current_user.git_token),
        "git_username": current_user.git_username,
    }


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
