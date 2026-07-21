"""Authentication service."""

from datetime import datetime, timedelta, timezone
from typing import Optional

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


def create_refresh_token(user_id: str) -> str:
    """创建 refresh token(P1-9)。

    Refresh token 与 access token 使用相同的签名密钥/算法,但:
        - 有效期更长(默认 7 天,由 ``settings.REFRESH_TOKEN_EXPIRE_MINUTES`` 控制)
        - payload 中 ``type`` 字段为 ``refresh``,与 access token 区分

    Args:
        user_id: 用户 ID(字符串形式)。

    Returns:
        签名后的 refresh token 字符串。
    """
    return create_access_token(
        {"sub": user_id, "type": "refresh"},
        expires_delta=timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
    )


def verify_refresh_token(token: str) -> Optional[str]:
    """验证 refresh token 并返回 user_id(P1-9)。

    Args:
        token: 待验证的 refresh token 字符串。

    Returns:
        校验通过返回 user_id 字符串;token 无效/过期/类型不匹配返回 None。
    """
    payload = decode_access_token(token)
    if payload is None:
        return None
    if payload.get("type") != "refresh":
        return None
    return payload.get("sub")


def create_token_for_user(user: User) -> TokenResponse:
    """Create a JWT token response for the given user.

    同时签发 access token 与 refresh token(P1-9)。

    Args:
        user: The authenticated user.

    Returns:
        A TokenResponse containing the access token, refresh token and user info.
    """
    token = create_access_token({"sub": str(user.id)})
    # 同时签发 refresh token,前端用于在 access token 过期后换新
    refresh = create_refresh_token(str(user.id))
    return TokenResponse(
        access_token=token,
        refresh_token=refresh,
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


# ---------------------------------------------------------------------------
# 登录失败计数(防暴力破解,基于 Redis)
# ---------------------------------------------------------------------------
# 登录失败次数上限,达到后锁定账号
LOGIN_FAIL_LIMIT = 5
# 锁定时长(分钟)
LOGIN_LOCK_MINUTES = 3


async def check_login_lock(redis, ip: str, username: str) -> tuple[bool, str]:
    """检查登录是否被锁定。

    Returns:
        (是否锁定, 提示消息)
    """
    key = f"login_fail:{ip}:{username}"
    count = await redis.get(key)
    if count and int(count) >= LOGIN_FAIL_LIMIT:
        ttl = await redis.ttl(key)
        minutes = max(1, ttl // 60)
        return True, f"账号已锁定,请 {minutes} 分钟后再试"
    return False, ""


async def record_login_fail(redis, ip: str, username: str) -> int:
    """记录登录失败,返回剩余尝试次数。"""
    key = f"login_fail:{ip}:{username}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, LOGIN_LOCK_MINUTES * 60)
    return LOGIN_FAIL_LIMIT - count


async def clear_login_fail(redis, ip: str, username: str):
    """登录成功后清除失败计数。"""
    key = f"login_fail:{ip}:{username}"
    await redis.delete(key)
