"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services.audit_service import create_audit_log
from app.services.auth_service import (
    authenticate_user,
    create_token_for_user,
    create_refresh_token,
    register_user,
    request_password_reset,
    reset_password,
    verify_refresh_token,
)
from app.utils.security import create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and return a JWT access token."""
    # 获取客户端 IP
    ip = http_request.client.host if http_request.client else "unknown"
    username = request.username

    # 检查登录是否被锁定(防暴力破解)
    redis = None
    try:
        from app.redis_client import get_redis
        from app.services.auth_service import (
            LOGIN_FAIL_LIMIT,
            check_login_lock,
            clear_login_fail,
            record_login_fail,
        )
        redis = await get_redis()
        locked, msg = await check_login_lock(redis, ip, username)
        if locked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=msg,
            )
    except HTTPException:
        raise
    except Exception:
        # Redis 不可用时降级,不阻塞登录
        redis = None

    user = await authenticate_user(db, request.username, request.password)
    if user is None:
        # 记录登录失败
        remaining = LOGIN_FAIL_LIMIT
        if redis is not None:
            try:
                remaining = await record_login_fail(redis, ip, username)
            except Exception:
                remaining = LOGIN_FAIL_LIMIT
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"用户名或密码错误,剩余尝试次数 {remaining}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 登录成功,清除失败计数
    if redis is not None:
        try:
            await clear_login_fail(redis, ip, username)
        except Exception:
            pass

    await create_audit_log(
        db=db,
        user_id=user.id,
        action="login",
        resource_type="auth",
        resource_id=str(user.id),
        details={"username": user.username},
    )

    return create_token_for_user(user)


@router.post("/refresh")
async def refresh_token_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """用 refresh token 换取新的 access token(P1-9)。

    请求体: ``{"refresh_token": "<token>"}``
    成功返回: ``{"access_token": "<new_token>", "token_type": "bearer"}``

    refresh token 无效/过期/类型不匹配均返回 401。
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请求体必须是 JSON",
        )
    refresh_token = body.get("refresh_token") if isinstance(body, dict) else None
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 refresh_token",
        )

    user_id = verify_refresh_token(refresh_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh_token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 生成新的 access token
    access_token = create_access_token({"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """P2-4: 登出,把当前 access token 加入 Redis 黑名单。

    黑名单 key 为 ``blacklist:<token>``,过期时间与 access token 一致,
    在 ``get_current_user`` 中检查,命中则拒绝请求。
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "", 1) if auth_header.startswith("Bearer ") else ""
    if token:
        try:
            from app.redis_client import get_redis
            redis = await get_redis()
            # token 存入黑名单,过期时间与 access token 一致
            await redis.setex(
                f"blacklist:{token}",
                settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "1",
            )
        except Exception:
            # Redis 不可用时降级:不阻断登出,只是该 token 在黑名单失效前仍可用
            pass

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="logout",
        resource_type="user",
        resource_id=str(current_user.id),
    )
    return {"message": "已登出"}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user (self-registration, always GUEST role)."""
    try:
        user = await register_user(db, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    await create_audit_log(
        db=db,
        user_id=user.id,
        action="register",
        resource_type="user",
        resource_id=str(user.id),
        details={"username": user.username, "email": user.email},
    )

    return UserResponse.model_validate(user)


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request a password reset link sent to the user's email.

    Always returns success to prevent email enumeration.
    """
    result = await request_password_reset(db, request.email)

    if result is not None:
        user, reset_token = result
        # Send reset email asynchronously via Celery
        from app.tasks.email_tasks import send_email

        reset_link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={reset_token}"
        subject = f"【{settings.APP_SHORT_NAME}】密码重置"
        body = (
            f"{user.full_name}，您好：\n\n"
            f"您正在重置 {settings.APP_NAME} 的密码。\n\n"
            f"请点击以下链接重置密码（1小时内有效）：\n{reset_link}\n\n"
            f"如非本人操作，请忽略此邮件。\n\n"
            f"{settings.APP_NAME}"
        )
        html = (
            f"<html><body>"
            f"<h2>密码重置</h2>"
            f"<p>{user.full_name}，您好：</p>"
            f"<p>您正在重置 {settings.APP_NAME} 的密码。</p>"
            f'<p><a href="{reset_link}" style="padding:10px 20px;background:#409EFF;color:white;text-decoration:none;border-radius:4px;">点击重置密码</a></p>'
            f'<p style="color:#999;font-size:12px;">链接1小时内有效。如非本人操作，请忽略此邮件。</p>'
            f"<hr><p style='color:#999;font-size:12px;'>{settings.APP_NAME}</p>"
            f"</body></html>"
        )
        send_email.delay(user.email, subject, body, html)

        await create_audit_log(
            db=db,
            user_id=user.id,
            action="forgot_password",
            resource_type="auth",
            resource_id=str(user.id),
            details={"email": request.email},
        )

    return {"message": "如果该邮箱已注册，重置链接已发送至您的邮箱"}


@router.post("/reset-password")
async def reset_password_endpoint(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset a user's password using a reset token."""
    try:
        user = await reset_password(db, request.token, request.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    await create_audit_log(
        db=db,
        user_id=user.id,
        action="reset_password",
        resource_type="auth",
        resource_id=str(user.id),
    )

    return {"message": "密码重置成功，请使用新密码登录"}
