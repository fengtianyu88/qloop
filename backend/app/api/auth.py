"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
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
    register_user,
    request_password_reset,
    reset_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and return a JWT access token."""
    user = await authenticate_user(db, request.username, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await create_audit_log(
        db=db,
        user_id=user.id,
        action="login",
        resource_type="auth",
        resource_id=str(user.id),
        details={"username": user.username},
    )

    return create_token_for_user(user)


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

        reset_link = f"http://localhost:5173/reset-password?token={reset_token}"
        subject = "【BMS SOX】密码重置"
        body = (
            f"{user.full_name}，您好：\n\n"
            f"您正在重置 BMS SOX 交付管理系统的密码。\n\n"
            f"请点击以下链接重置密码（1小时内有效）：\n{reset_link}\n\n"
            f"如非本人操作，请忽略此邮件。\n\n"
            f"BMS SOX 交付管理系统"
        )
        html = (
            f"<html><body>"
            f"<h2>密码重置</h2>"
            f"<p>{user.full_name}，您好：</p>"
            f"<p>您正在重置 BMS SOX 交付管理系统的密码。</p>"
            f'<p><a href="{reset_link}" style="padding:10px 20px;background:#409EFF;color:white;text-decoration:none;border-radius:4px;">点击重置密码</a></p>'
            f'<p style="color:#999;font-size:12px;">链接1小时内有效。如非本人操作，请忽略此邮件。</p>'
            f"<hr><p style='color:#999;font-size:12px;'>BMS SOX 交付管理系统</p>"
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
