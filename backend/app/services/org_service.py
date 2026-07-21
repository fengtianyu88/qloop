"""Organization management service."""

import uuid
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import AdminScope, OrgUnit
from app.schemas.organization import OrgTreeResponse, OrgUnitCreate, OrgUnitUpdate


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
        ValueError: If parent_id is provided but does not exist.
    """
    if org_create.parent_id is not None:
        parent = await get_org_unit_by_id(db, org_create.parent_id)
        if parent is None:
            raise ValueError(
                f"Parent org unit '{org_create.parent_id}' does not exist"
            )

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
    """Get the full organization tree starting from root nodes.

    Args:
        db: The async database session.

    Returns:
        A list of OrgTreeResponse representing root nodes with children,
        each carrying the list of admin user full_names that govern it.
    """
    result = await db.execute(
        select(OrgUnit)
        .where(OrgUnit.is_active == True)  # noqa: E712
        .order_by(OrgUnit.created_at)
    )
    all_units = list(result.scalars().all())

    # Build manager_map: org_unit_id -> [full_name, ...]
    manager_map: Dict[uuid.UUID, List[str]] = {}
    if all_units:
        from app.models.organization import AdminScope
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
    from app.models.organization import OrgUnit, AdminScope
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
    """Update an organizational unit.

    Args:
        db: The async database session.
        org_id: The ID of the org unit to update.
        org_update: The fields to update.

    Returns:
        The updated OrgUnit object, or ``None`` if not found.
    """
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

    for field, value in update_data.items():
        setattr(org_unit, field, value)

    await db.commit()
    await db.refresh(org_unit)
    return org_unit


async def set_admin_scope(
    db: AsyncSession, user_id: uuid.UUID, org_unit_id: uuid.UUID
) -> AdminScope:
    """Set an admin scope for a user (create if not exists).

    Args:
        db: The async database session.
        user_id: The user ID.
        org_unit_id: The org unit ID.

    Returns:
        The AdminScope object.

    Raises:
        ValueError: If the org unit does not exist or the scope already exists.
    """
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
    """Get all admin scopes for a user.

    Args:
        db: The async database session.
        user_id: The user ID.

    Returns:
        A list of AdminScope objects.
    """
    result = await db.execute(
        select(AdminScope).where(AdminScope.user_id == user_id)
    )
    return list(result.scalars().all())


async def delete_admin_scope(db: AsyncSession, scope_id: uuid.UUID) -> bool:
    """Delete an admin scope by ID.

    Args:
        db: The async database session.
        scope_id: The admin scope ID.

    Returns:
        True if deleted, False if not found.
    """
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
