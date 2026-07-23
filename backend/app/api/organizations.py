"""Organization management API routes."""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles
from app.models.user import SystemRole, User
from app.schemas.organization import (
    AdminScopeCreate,
    AdminScopeResponse,
    OrgTreeResponse,
    OrgTypeCreate,
    OrgTypeResponse,
    OrgUnitCreate,
    OrgUnitResponse,
    OrgUnitUpdate,
)
from app.services.audit_service import create_audit_log
from app.services.org_service import (
    create_org_type,
    create_org_unit,
    delete_admin_scope,
    delete_org_type,
    delete_org_unit,
    get_admin_scopes,
    get_admin_scopes_for_org,
    get_org_tree,
    get_org_types,
    set_admin_scope,
    update_org_unit,
)

router = APIRouter(prefix="/api/organizations", tags=["organizations"])
# v1.5.2: 组织类型管理路由
org_type_router = APIRouter(prefix="/api/org-types", tags=["org-types"])


# ===========================================================================
# 组织类型管理 v1.5.2
# ===========================================================================

@org_type_router.get("", response_model=List[OrgTypeResponse])
async def list_org_types_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.ADMIN, SystemRole.SUPER_ADMIN)),
):
    """获取所有组织类型(按 sort_order 排序)。"""
    org_types = await get_org_types(db=db)
    # 批量填充 created_by_name
    result = []
    for ot in org_types:
        resp = await _enrich_org_type_response(db, ot)
        result.append(resp)
    return result


@org_type_router.post(
    "",
    response_model=OrgTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_org_type_endpoint(
    org_type_create: OrgTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(SystemRole.ADMIN, SystemRole.SUPER_ADMIN)
    ),
):
    """新建组织类型(ADMIN, SUPER_ADMIN)。"""
    try:
        org_type = await create_org_type(
            db=db, org_type_create=org_type_create, created_by=current_user.id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="create_org_type",
        resource_type="org_type",
        resource_id=str(org_type.id),
        details={"code": org_type.code, "name": org_type.name},
    )

    return await _enrich_org_type_response(db, org_type)


@org_type_router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org_type_endpoint(
    type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.SUPER_ADMIN)),
):
    """删除组织类型(SUPER_ADMIN only)。

    拒绝条件:
    - is_system=True(系统预设不可删)
    - 存在引用此类型的 org_unit
    """
    try:
        deleted = await delete_org_type(db=db, type_id=type_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization type not found",
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="delete_org_type",
        resource_type="org_type",
        resource_id=str(type_id),
        details={},
    )
    return None


async def _enrich_org_type_response(db: AsyncSession, org_type) -> OrgTypeResponse:
    """填充 created_by_name 字段。"""
    resp = OrgTypeResponse.model_validate(org_type)
    if org_type.created_by is not None:
        from sqlalchemy import select as _select
        from app.models.user import User as _User
        user_result = await db.execute(
            _select(_User.full_name).where(_User.id == org_type.created_by)
        )
        full_name = user_result.scalar_one_or_none()
        resp.created_by_name = full_name
    return resp


# ===========================================================================
# 组织单元管理
# ===========================================================================

@router.get("/tree", response_model=List[OrgTreeResponse])
async def get_org_tree_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(SystemRole.ADMIN, SystemRole.SUPER_ADMIN)
    ),
):
    """Get the full organization tree (ADMIN, SUPER_ADMIN only)."""
    return await get_org_tree(db=db)


@router.post(
    "",
    response_model=OrgUnitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_org_unit_endpoint(
    org_create: OrgUnitCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.SUPER_ADMIN)),
):
    """Create a new organizational unit (SUPER_ADMIN only)."""
    try:
        org_unit = await create_org_unit(db=db, org_create=org_create)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="create_org_unit",
        resource_type="org_unit",
        resource_id=str(org_unit.id),
        details={"name": org_unit.name, "org_type": org_unit.org_type},
    )

    return OrgUnitResponse.model_validate(org_unit)


@router.put("/{org_id}", response_model=OrgUnitResponse)
async def update_org_unit_endpoint(
    org_id: uuid.UUID,
    org_update: OrgUnitUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.SUPER_ADMIN)),
):
    """Update an organizational unit (SUPER_ADMIN only)."""
    try:
        org_unit = await update_org_unit(
            db=db, org_id=org_id, org_update=org_update
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    if org_unit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization unit not found",
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="update_org_unit",
        resource_type="org_unit",
        resource_id=str(org_unit.id),
        details=org_update.model_dump(exclude_unset=True),
    )

    return OrgUnitResponse.model_validate(org_unit)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org_unit_endpoint(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.SUPER_ADMIN)),
):
    """删除组织单元(SUPER_ADMIN only)。

    拒绝条件:存在子节点 / 存在关联用户。
    """
    try:
        deleted = await delete_org_unit(db=db, org_id=org_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization unit not found",
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="delete_org_unit",
        resource_type="org_unit",
        resource_id=str(org_id),
        details={},
    )
    return None

@router.post(
    "/admin-scopes",
    response_model=AdminScopeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def set_admin_scope_endpoint(
    scope_create: AdminScopeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.SUPER_ADMIN)),
):
    """Set an admin scope for a user (SUPER_ADMIN only)."""
    try:
        admin_scope = await set_admin_scope(
            db=db,
            user_id=scope_create.user_id,
            org_unit_id=scope_create.org_unit_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="set_admin_scope",
        resource_type="admin_scope",
        resource_id=str(admin_scope.id),
        details={
            "target_user_id": str(scope_create.user_id),
            "org_unit_id": str(scope_create.org_unit_id),
        },
    )

    return AdminScopeResponse.model_validate(admin_scope)


@router.get("/admin-scopes/{user_id}", response_model=List[AdminScopeResponse])
async def get_admin_scopes_endpoint(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.SUPER_ADMIN)),
):
    """Get all admin scopes for a user (SUPER_ADMIN only)."""
    scopes = await get_admin_scopes(db=db, user_id=user_id)
    return [AdminScopeResponse.model_validate(s) for s in scopes]


@router.delete("/admin-scopes/{scope_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_scope_endpoint(
    scope_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(SystemRole.SUPER_ADMIN)),
):
    """Delete an admin scope (SUPER_ADMIN only)."""
    deleted = await delete_admin_scope(db=db, scope_id=scope_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin scope not found",
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="delete_admin_scope",
        resource_type="admin_scope",
        resource_id=str(scope_id),
        details={},
    )
    return None


@router.get("/org-units/{org_id}/admin-scopes")
async def get_org_admin_scopes_endpoint(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_roles(SystemRole.ADMIN, SystemRole.SUPER_ADMIN)
    ),
):
    """List all managers (admin scopes) for an org unit (ADMIN+)."""
    return await get_admin_scopes_for_org(db=db, org_unit_id=org_id)
