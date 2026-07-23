"""Organization models: OrgTypeModel, OrgUnit and AdminScope."""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OrgTypeModel(Base):
    """组织类型(支持自定义)。

    v1.5.2: 替代原有硬编码的 OrgType 枚举,支持管理员/超级管理员自定义添加。
    系统预设类型(department/division/group)is_system=True,不可删除。
    """

    __tablename__ = "org_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    created_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by],
    )

    def __repr__(self) -> str:
        return f"<OrgTypeModel(code={self.code!r}, name={self.name!r}, is_system={self.is_system})>"


class OrgUnit(Base):
    """Organizational unit (department / division / group / custom) with tree hierarchy."""

    __tablename__ = "org_units"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # v1.5.2: org_type 从 SAEnum 改为 String,存储 org_types.code(小写)
    org_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="department",
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_units.id"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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

    # Self-referential relationships
    parent: Mapped[Optional["OrgUnit"]] = relationship(
        "OrgUnit",
        remote_side="OrgUnit.id",
        back_populates="children",
    )
    children: Mapped[List["OrgUnit"]] = relationship(
        "OrgUnit", back_populates="parent", cascade="all, delete-orphan"
    )

    # Other relationships
    users: Mapped[List["User"]] = relationship(
        "User", back_populates="org_unit"
    )
    admin_scopes: Mapped[List["AdminScope"]] = relationship(
        "AdminScope", back_populates="org_unit", cascade="all, delete-orphan"
    )


class AdminScope(Base):
    """Defines which org units a user can administer."""

    __tablename__ = "admin_scopes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    org_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_units.id"), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="admin_scopes")
    org_unit: Mapped["OrgUnit"] = relationship(
        "OrgUnit", back_populates="admin_scopes"
    )
