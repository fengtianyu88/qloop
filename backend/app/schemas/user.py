"""User-related Pydantic schemas."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import SystemRole


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


class ForgotPasswordRequest(BaseModel):
    """Schema for requesting a password reset."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Schema for resetting a password with a token."""

    token: str
    new_password: str = Field(..., min_length=6, max_length=128)
