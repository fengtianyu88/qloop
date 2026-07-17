"""Authentication service."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User, SystemRole
from app.schemas.user import (
    ForgotPasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.utils.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> User | None:
    """Authenticate a user by username and password.

    Args:
        db: The async database session.
        username: The username to look up.
        password: The plain-text password to verify.

    Returns:
        The User object if authentication succeeds, ``None`` otherwise.
    """
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    return user


def create_token_for_user(user: User) -> TokenResponse:
    """Create a JWT token response for the given user.

    Args:
        user: The authenticated user.

    Returns:
        A TokenResponse containing the access token and user info.
    """
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        system_role=user.system_role,
    )


async def register_user(db: AsyncSession, data: RegisterRequest) -> User:
    """Register a new user (self-registration, always GUEST role).

    Args:
        db: The async database session.
        data: The registration data.

    Returns:
        The created User object.

    Raises:
        ValueError: If username or email already exists.
    """
    existing_username = await db.execute(
        select(User).where(User.username == data.username)
    )
    if existing_username.scalar_one_or_none() is not None:
        raise ValueError("用户名已存在")

    existing_email = await db.execute(
        select(User).where(User.email == data.email)
    )
    if existing_email.scalar_one_or_none() is not None:
        raise ValueError("邮箱已被注册")

    user = User(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        system_role=SystemRole.GUEST,
        department=data.department,
        section=data.section,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def request_password_reset(
    db: AsyncSession, email: str
) -> User | None:
    """Generate a password reset token for the given email.

    Args:
        db: The async database session.
        email: The email address to send the reset link to.

    Returns:
        The User object if found, ``None`` otherwise.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None

    # Generate a short-lived reset token (1 hour)
    reset_token = create_access_token(
        {"sub": str(user.id), "purpose": "password_reset"},
        expires_delta=timedelta(hours=1),
    )
    return user, reset_token


async def reset_password(
    db: AsyncSession, token: str, new_password: str
) -> User:
    """Reset a user's password using a reset token.

    Args:
        db: The async database session.
        token: The password reset JWT token.
        new_password: The new plain-text password.

    Returns:
        The updated User object.

    Raises:
        ValueError: If the token is invalid or expired.
    """
    payload = decode_access_token(token)
    if payload is None:
        raise ValueError("重置链接无效或已过期")

    if payload.get("purpose") != "password_reset":
        raise ValueError("重置链接无效")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise ValueError("用户不存在或已禁用")

    user.hashed_password = hash_password(new_password)
    await db.commit()
    await db.refresh(user)
    return user
