"""FastAPI dependencies for authentication and authorization."""

import uuid
from typing import Callable

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import SystemRole, User
from app.utils.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
# 可选 OAuth2 scheme:不自动报 401,用于 SSE 端点
# EventSource 不能自定义 header,需要从 query 参数获取 token
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login", auto_error=False
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the JWT token and return the corresponding user.

    Raises:
        HTTPException 401 if the token is invalid or the user does not exist.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    # P2-4: 检查 token 是否在黑名单中(已登出)
    try:
        from app.redis_client import get_redis
        redis = await get_redis()
        is_blacklisted = await redis.get(f"blacklist:{token}")
        if is_blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 已失效",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception:
        # Redis 不可用时降级,不阻断请求(只是黑名单不生效)
        pass

    user_id_str: str | None = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


def require_roles(
    *roles: SystemRole,
) -> Callable:
    """Return a dependency that checks the current user has one of the given roles.

    Usage::

        @router.get("/", dependencies=[Depends(require_roles(SystemRole.ADMIN))])
        async def my_endpoint(...): ...
    """

    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.system_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(r.value for r in roles)}",
            )
        return current_user

    return role_checker


async def get_current_user_sse(
    token: str | None = Depends(oauth2_scheme_optional),
    query_token: str | None = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """SSE 端点专用认证:同时支持 Authorization header 和 query 参数 token。

    EventSource API 不能自定义 header,所以前端通过 ?token=xxx 传递 JWT。
    其它逻辑与 get_current_user 一致。
    """
    actual_token = token or query_token
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not actual_token:
        raise credentials_exception

    payload = decode_access_token(actual_token)
    if payload is None:
        raise credentials_exception

    # P2-4: 检查 token 是否在黑名单中(SSE 端点同样需要)
    try:
        from app.redis_client import get_redis
        redis = await get_redis()
        is_blacklisted = await redis.get(f"blacklist:{actual_token}")
        if is_blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 已失效",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception:
        # Redis 不可用时降级
        pass

    user_id_str: str | None = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user
