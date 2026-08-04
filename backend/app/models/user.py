"""User model and SystemRole enum."""

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SystemRole(str, Enum):
    """System-level roles for access control."""

    GUEST = "guest"
    DEVELOPER = "developer"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class User(Base):
    """Application user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    system_role: Mapped[SystemRole] = mapped_column(
        SAEnum(
            SystemRole,
            name="system_role",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=SystemRole.GUEST,
    )
    org_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_units.id"), nullable=True
    )
    department: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    section: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # Git 推送凭据(用于版本释放后推送交付物到项目 Git 仓库)
    git_username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    git_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 计算@property:是否已配置 Git token(用于 UserResponse.has_git_token)
    # Pydantic 的 from_attributes 会读取该属性,无需在数据库中存储。
    @property
    def has_git_token(self) -> bool:
        """返回当前用户是否已配置 Git token(不暴露 token 原文)。"""
        return bool(self.git_token)

    # Relationships
    org_unit = relationship("OrgUnit", back_populates="users")
    admin_scopes: Mapped[List["AdminScope"]] = relationship(
        "AdminScope", back_populates="user", cascade="all, delete-orphan"
    )
    managed_projects: Mapped[List["Project"]] = relationship(
        "Project", back_populates="pm", foreign_keys="Project.pm_user_id"
    )
    project_memberships: Mapped[List["ProjectMember"]] = relationship(
        "ProjectMember", back_populates="user"
    )
