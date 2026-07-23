"""Organization management service."""

import uuid
from typing import Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import AdminScope, OrgTypeModel, OrgUnit
from app.schemas.organization import (
    OrgTreeResponse,
    OrgTypeCreate,
    OrgUnitCreate,
    OrgUnitUpdate,
)


# ===========================================================================
# 组织类型管理 v1.5.2
# ===========================================================================

async def get_org_types(db: AsyncSession) -> List[OrgTypeModel]:
    """获取所有启用的组织类型,按 sort_order 排序。"""
    result = await db.execute(
        select(OrgTypeModel)
        .where(OrgTypeModel.is_active == True)  # noqa: E712
        .order_by(OrgTypeModel.sort_order, OrgTypeModel.created_at)
    )
    return list(result.scalars().all())


async def get_org_type_by_code(db: AsyncSession, code: str) -> Optional[OrgTypeModel]:
    """按 code 查找组织类型。"""
    result = await db.execute(
        select(OrgTypeModel).where(OrgTypeModel.code == code)
    )
    return result.scalar_one_or_none()


async def create_org_type(
    db: AsyncSession, org_type_create: OrgTypeCreate, created_by: uuid.UUID
) -> OrgTypeModel:
    """创建组织类型。

    Raises:
        ValueError: code 已存在。
    """
    # 检查 code 是否已存在(不区分大小写)
    existing = await db.execute(
        select(OrgTypeModel).where(func.lower(OrgTypeModel.code) == org_type_create.code.lower())
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"组织类型代码 '{org_type_create.code}' 已存在")

    org_type = OrgTypeModel(
        code=org_type_create.code.lower().strip(),
        name=org_type_create.name.strip(),
        is_system=False,
        sort_order=org_type_create.sort_order,
        created_by=created_by,
    )
    db.add(org_type)
    await db.commit()
    await db.refresh(org_type)
    return org_type


async def delete_org_type(db: AsyncSession, type_id: uuid.UUID) -> bool:
    """删除组织类型。

    安全策略:
    - is_system=True 拒绝删除(系统预设)
    - 存在引用此类型的 org_unit 拒绝删除

    Returns:
        True 表示删除成功;False 表示未找到。
    """
    result = await db.execute(
        select(OrgTypeModel).where(OrgTypeModel.id == type_id)
    )
    org_type = result.scalar_one_or_none()
    if org_type is None:
        return False

    if org_type.is_system:
        raise ValueError("系统预设类型不可删除")

    # 检查是否有 org_unit 引用此类型
    ref_result = await db.execute(
        select(OrgUnit).where(OrgUnit.org_type == org_type.code).limit(1)
    )
    if ref_result.scalar_one_or_none() is not None:
        raise ValueError(f"存在使用类型 '{org_type.name}' 的组织单元,请先迁移后再删除")

    await db.delete(org_type)
    await db.commit()
    return True


# ===========================================================================
# 组织单元管理
# ===========================================================================

async def create_org_unit(
    db: AsyncSession, org_create: OrgUnitCreate
) -> OrgUnit:
    """Create a new organizational unit.

    Args:
        db: The async database session.
        org_create: The org unit creation data.

    Returns:
        The created OrgUnit object.

    Raises:
        ValueError: If parent_id is provided but does not exist,
                   or if org_type does not exist in org_types table.
    """
    if org_create.parent_id is not None:
        parent = await get_org_unit_by_id(db, org_create.parent_id)
        if parent is None:
            raise ValueError(
                f"Parent org unit '{org_create.parent_id}' does not exist"
            )

    # v1.5.2: 校验 org_type 是否存在于 org_types 表
    org_type_obj = await get_org_type_by_code(db, org_create.org_type)
    if org_type_obj is None:
        raise ValueError(f"组织类型 '{org_create.org_type}' 不存在")

    org_unit = OrgUnit(
        name=org_create.name,
        org_type=org_create.org_type,
        parent_id=org_create.parent_id,
        description=org_create.description,
        is_active=org_create.is_active,
    )
    db.add(org_unit)
    await db.commit()
    await db.refresh(org_unit)
    return org_unit


async def _build_tree(
    all_units: List[OrgUnit],
    manager_map: Dict[uuid.UUID, List[str]],
) -> List[OrgTreeResponse]:
    """Build a tree of OrgTreeResponse from a flat list of OrgUnits.

    ``manager_map`` is a mapping ``org_unit_id -> [full_name, ...]`` of
    users who have an admin scope on that unit.
    """
    # Group units by parent_id
    children_map: Dict[Optional[uuid.UUID], List[OrgUnit]] = {}
    for unit in all_units:
        parent_id = unit.parent_id
        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(unit)

    def build_node(unit: OrgUnit) -> OrgTreeResponse:
        child_units = children_map.get(unit.id, [])
        children = [build_node(child) for child in child_units]
        return OrgTreeResponse(
            id=unit.id,
            name=unit.name,
            org_type=unit.org_type,
            parent_id=unit.parent_id,
            description=unit.description,
            is_active=unit.is_active,
            created_at=unit.created_at,
            updated_at=unit.updated_at,
            manager_names=manager_map.get(unit.id, []),
            children=children,
        )

    # Root units have parent_id == None
    root_units = children_map.get(None, [])
    return [build_node(unit) for unit in root_units]


async def get_org_tree(db: AsyncSession) -> List[OrgTreeResponse]:
    """Get the full organization tree starting from root nodes."""
    result = await db.execute(
        select(OrgUnit)
        .where(OrgUnit.is_active == True)  # noqa: E712
        .order_by(OrgUnit.created_at)
    )
    all_units = list(result.scalars().all())

    # Build manager_map: org_unit_id -> [full_name, ...]
    manager_map: Dict[uuid.UUID, List[str]] = {}
    if all_units:
        from app.models.user import User
        unit_ids = [u.id for u in all_units]
        res = await db.execute(
            select(AdminScope.org_unit_id, User.full_name)
            .select_from(AdminScope)
            .join(User, AdminScope.user_id == User.id)
            .where(AdminScope.org_unit_id.in_(unit_ids))
        )
        for row in res.all():
            manager_map.setdefault(row.org_unit_id, []).append(row.full_name)

    return await _build_tree(all_units, manager_map)


async def get_org_unit_by_id(
    db: AsyncSession, org_id: uuid.UUID
) -> Optional[OrgUnit]:
    """Get an org unit by ID."""
    result = await db.execute(select(OrgUnit).where(OrgUnit.id == org_id))
    return result.scalar_one_or_none()


async def delete_org_unit(db: AsyncSession, org_id: uuid.UUID) -> bool:
    """删除组织单元。

    安全策略:
    - 存在子节点时拒绝(避免级联删除误伤);
    - 存在关联用户时拒绝(需先迁移用户);
    - admin_scopes 通过 ORM cascade 自动清理。

    Returns:
        True 表示删除成功;False 表示未找到。
    """
    from sqlalchemy import select as _select
    from app.models.user import User

    org_unit = await get_org_unit_by_id(db, org_id)
    if org_unit is None:
        return False

    # 检查子节点
    child_result = await db.execute(
        _select(OrgUnit).where(OrgUnit.parent_id == org_id).limit(1)
    )
    if child_result.scalar_one_or_none() is not None:
        raise ValueError("该组织单元存在子节点,请先删除子节点")

    # 检查关联用户
    user_result = await db.execute(
        _select(User).where(User.org_unit_id == org_id).limit(1)
    )
    if user_result.scalar_one_or_none() is not None:
        raise ValueError("该组织单元下存在用户,请先迁移用户到其他组织单元")

    await db.delete(org_unit)
    await db.commit()
    return True


async def update_org_unit(
    db: AsyncSession, org_id: uuid.UUID, org_update: OrgUnitUpdate
) -> Optional[OrgUnit]:
    """Update an organizational unit."""
    org_unit = await get_org_unit_by_id(db, org_id)
    if org_unit is None:
        return None

    update_data = org_update.model_dump(exclude_unset=True)

    if "parent_id" in update_data and update_data["parent_id"] is not None:
        if update_data["parent_id"] == org_id:
            raise ValueError("An org unit cannot be its own parent")
        parent = await get_org_unit_by_id(db, update_data["parent_id"])
        if parent is None:
            raise ValueError(
                f"Parent org unit '{update_data['parent_id']}' does not exist"
            )

    # v1.5.2: 校验 org_type 是否存在
    if "org_type" in update_data and update_data["org_type"] is not None:
        org_type_obj = await get_org_type_by_code(db, update_data["org_type"])
        if org_type_obj is None:
            raise ValueError(f"组织类型 '{update_data['org_type']}' 不存在")

    for field, value in update_data.items():
        setattr(org_unit, field, value)

    await db.commit()
    await db.refresh(org_unit)
    return org_unit


# ===========================================================================
# 管理员范围管理
# ===========================================================================

async def set_admin_scope(
    db: AsyncSession, user_id: uuid.UUID, org_unit_id: uuid.UUID
) -> AdminScope:
    """Set an admin scope for a user (create if not exists)."""
    org_unit = await get_org_unit_by_id(db, org_unit_id)
    if org_unit is None:
        raise ValueError(f"Org unit '{org_unit_id}' does not exist")

    # Check if already exists
    existing = await db.execute(
        select(AdminScope).where(
            AdminScope.user_id == user_id,
            AdminScope.org_unit_id == org_unit_id,
        )
    )
    existing_scope = existing.scalar_one_or_none()
    if existing_scope is not None:
        return existing_scope

    admin_scope = AdminScope(user_id=user_id, org_unit_id=org_unit_id)
    db.add(admin_scope)
    await db.commit()
    await db.refresh(admin_scope)
    return admin_scope


async def get_admin_scopes(
    db: AsyncSession, user_id: uuid.UUID
) -> List[AdminScope]:
    """Get all admin scopes for a user."""
    result = await db.execute(
        select(AdminScope).where(AdminScope.user_id == user_id)
    )
    return list(result.scalars().all())


async def delete_admin_scope(db: AsyncSession, scope_id: uuid.UUID) -> bool:
    """Delete an admin scope by ID."""
    result = await db.execute(
        select(AdminScope).where(AdminScope.id == scope_id)
    )
    scope = result.scalar_one_or_none()
    if scope is None:
        return False
    await db.delete(scope)
    await db.commit()
    return True


async def get_admin_scopes_for_org(
    db: AsyncSession, org_unit_id: uuid.UUID
) -> List[dict]:
    """Get all admin scopes for an org unit, joined with user info.

    Returns a list of dicts: { id, user_id, full_name, username }.
    """
    from app.models.user import User
    res = await db.execute(
        select(AdminScope.id, AdminScope.user_id, User.full_name, User.username)
        .select_from(AdminScope)
        .join(User, AdminScope.user_id == User.id)
        .where(AdminScope.org_unit_id == org_unit_id)
    )
    return [
        {"id": str(row.id), "user_id": str(row.user_id),
         "full_name": row.full_name, "username": row.username}
        for row in res.all()
    ]
