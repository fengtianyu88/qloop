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
) -> List[OrgTreeResponse]:
    """Build a tree of OrgTreeResponse from a flat list of OrgUnits."""
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
        A list of OrgTreeResponse representing root nodes with children.
    """
    result = await db.execute(
        select(OrgUnit)
        .where(OrgUnit.is_active == True)  # noqa: E712
        .order_by(OrgUnit.created_at)
    )
    all_units = list(result.scalars().all())
    return await _build_tree(all_units)


async def get_org_unit_by_id(
    db: AsyncSession, org_id: uuid.UUID
) -> Optional[OrgUnit]:
    """Get an org unit by ID."""
    result = await db.execute(select(OrgUnit).where(OrgUnit.id == org_id))
    return result.scalar_one_or_none()


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
