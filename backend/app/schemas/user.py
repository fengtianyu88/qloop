"""User-related Pydantic schemas."""

import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import SystemRole


# ---------------------------------------------------------------------------
# 密码强度规则(P1-8)
# ---------------------------------------------------------------------------
# 至少 8 位,且同时包含字母和数字
PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def _check_password_strength(value: str) -> str:
    """校验密码强度:至少 8 位,且同时包含字母和数字。

    Args:
        value: 待校验的明文密码。

    Returns:
        校验通过的密码(原样返回)。

    Raises:
        ValueError: 密码不符合强度要求。
    """
    if not PASSWORD_PATTERN.match(value):
        raise ValueError("密码必须至少 8 位,且包含字母和数字")
    return value


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    full_name: str = Field(..., max_length=200)
    password: str = Field(..., min_length=6, max_length=128)
    system_role: SystemRole = SystemRole.GUEST
    org_unit_id: Optional[uuid.UUID] = None
    department: Optional[str] = None
    section: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """校验密码强度(P1-8)。"""
        return _check_password_strength(v)


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    system_role: Optional[SystemRole] = None
    org_unit_id: Optional[uuid.UUID] = None
    department: Optional[str] = None
    section: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """校验密码强度(P1-8);未传密码时跳过。"""
        if v is None:
            return v
        return _check_password_strength(v)


class UserResponse(BaseModel):
    """Schema for user responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    full_name: str
    system_role: SystemRole
    org_unit_id: Optional[uuid.UUID] = None
    department: Optional[str] = None
    section: Optional[str] = None
    # Git 推送凭据(仅返回用户名,不返回 token 原文)
    git_username: Optional[str] = None
    # 标记是否已配置 Git token(不返回 token 原文,由 ORM @property 推断)
    has_git_token: bool = False
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    """Schema for login requests."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Schema for authentication token responses."""

    access_token: str
    # Refresh token(P1-9):登录时一并下发,前端用于在 access token 过期后换新
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user_id: uuid.UUID
    username: str
    system_role: SystemRole


class RegisterRequest(BaseModel):
    """Schema for user self-registration."""

    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    full_name: str = Field(..., max_length=200)
    password: str = Field(..., min_length=6, max_length=128)
    department: Optional[str] = None
    section: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """校验密码强度(P1-8)。"""
        return _check_password_strength(v)


class ForgotPasswordRequest(BaseModel):
    """Schema for requesting a password reset."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Schema for resetting a password with a token."""

    token: str
    new_password: str = Field(..., min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """校验新密码强度(P1-8)。"""
        return _check_password_strength(v)


class ChangePasswordRequest(BaseModel):
    """Schema for changing the current user's own password."""

    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """校验新密码强度(P1-8)。"""
        return _check_password_strength(v)


class UserGitCredentialsRequest(BaseModel):
    """Schema for updating the current user's own Git push credentials.

    用于版本释放后,以当前用户(项目经理)的 Git 账号推送到项目 Git 仓库。
    git_token 可以传空字符串表示清除。
    """

    git_username: Optional[str] = Field(None, max_length=200)
    git_token: Optional[str] = Field(None, max_length=500)
