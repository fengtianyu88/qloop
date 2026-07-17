"""Organization models: OrgUnit and AdminScope."""

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
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OrgType(str, Enum):
    """Type of organizational unit."""

    DEPARTMENT = "department"
    DIVISION = "division"
    GROUP = "group"


class OrgUnit(Base):
    """Organizational unit (department / division / group) with tree hierarchy."""

    __tablename__ = "org_units"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    org_type: Mapped[OrgType] = mapped_column(
        SAEnum(OrgType, name="org_type"),
        nullable=False,
        default=OrgType.DEPARTMENT,
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
