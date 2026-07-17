"""User management service."""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import AdminScope, OrgUnit
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.utils.security import hash_password


async def create_user(db: AsyncSession, user_create: UserCreate) -> User:
    """Create a new user.

    Args:
        db: The async database session.
        user_create: The user creation data.

    Returns:
        The created User object.

    Raises:
        ValueError: If username or email already exists.
    """
    # Check for existing username
    existing = await db.execute(
        select(User).where(User.username == user_create.username)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Username '{user_create.username}' already exists")

    # Check for existing email
    existing = await db.execute(
        select(User).where(User.email == user_create.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Email '{user_create.email}' already exists")

    user = User(
        username=user_create.username,
        email=user_create.email,
        full_name=user_create.full_name,
        hashed_password=hash_password(user_create.password),
        system_role=user_create.system_role,
        org_unit_id=user_create.org_unit_id,
        department=user_create.department,
        section=user_create.section,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(
    db: AsyncSession, user_id: uuid.UUID
) -> Optional[User]:
    """Get a user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_users_paginated(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    org_unit_id: Optional[uuid.UUID] = None,
) -> Tuple[List[User], int]:
    """Get a paginated list of users with optional filtering.

    Args:
        db: The async database session.
        page: Page number (1-based).
        page_size: Number of items per page.
        search: Optional search term for username, email, or full_name.
        org_unit_id: Optional org unit filter (includes child org units).

    Returns:
        A tuple of (list of users, total count).
    """
    query = select(User)

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                User.username.ilike(search_pattern),
                User.email.ilike(search_pattern),
                User.full_name.ilike(search_pattern),
            )
        )

    if org_unit_id is not None:
        # Include child org unit IDs
        org_ids = await get_child_org_unit_ids(db, org_unit_id)
        query = query.where(User.org_unit_id.in_(org_ids))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(User.created_at.desc())

    result = await db.execute(query)
    users = list(result.scalars().all())

    return users, total


async def update_user(
    db: AsyncSession, user_id: uuid.UUID, user_update: UserUpdate
) -> Optional[User]:
    """Update a user.

    Args:
        db: The async database session.
        user_id: The ID of the user to update.
        user_update: The fields to update.

    Returns:
        The updated User object, or ``None`` if not found.
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        return None

    update_data = user_update.model_dump(exclude_unset=True)

    # Handle password update separately
    password = update_data.pop("password", None)
    if password:
        user.hashed_password = hash_password(password)

    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Soft-delete a user by setting ``is_active`` to False.

    Args:
        db: The async database session.
        user_id: The ID of the user to deactivate.

    Returns:
        True if the user was deactivated, False if not found.
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        return False

    user.is_active = False
    await db.commit()
    return True


async def get_child_org_unit_ids(
    db: AsyncSession, org_unit_id: uuid.UUID
) -> List[uuid.UUID]:
    """Recursively get all descendant org unit IDs (including the given one).

    Args:
        db: The async database session.
        org_unit_id: The root org unit ID.

    Returns:
        A list of all org unit IDs in the subtree (including the root).
    """
    all_ids: List[uuid.UUID] = [org_unit_id]
    queue: List[uuid.UUID] = [org_unit_id]

    while queue:
        current = queue.pop(0)
        result = await db.execute(
            select(OrgUnit.id).where(OrgUnit.parent_id == current)
        )
        children = result.scalars().all()
        for child in children:
            all_ids.append(child)
            queue.append(child)

    return all_ids


async def get_admin_scope_org_ids(
    db: AsyncSession, user_id: uuid.UUID
) -> List[uuid.UUID]:
    """Get all org unit IDs a user can administer (including descendants).

    Args:
        db: The async database session.
        user_id: The user ID.

    Returns:
        A list of all org unit IDs in the user's admin scope.
    """
    result = await db.execute(
        select(AdminScope.org_unit_id).where(AdminScope.user_id == user_id)
    )
    direct_org_ids = result.scalars().all()

    all_ids: set = set()
    for org_id in direct_org_ids:
        child_ids = await get_child_org_unit_ids(db, org_id)
        all_ids.update(child_ids)

    return list(all_ids)
