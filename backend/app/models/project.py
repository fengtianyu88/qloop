"""Project models: Project, ProjectMember, Version, Release, ExternalRecipient."""

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProjectRole(str, Enum):
    """Role of a user within a project."""

    PROJECT_MANAGER = "project_manager"
    DEVELOPER = "developer"
    TESTER = "tester"
    EXTERNAL_EXPERT = "external_expert"


class ReleaseStatus(str, Enum):
    """Status of a release in the review pipeline."""

    DRAFT = "draft"
    CODE_PENDING_REVIEW = "code_pending_review"
    TEST_PENDING_REVIEW = "test_pending_review"
    EXPERT_PENDING_REVIEW = "expert_pending_review"
    PENDING_CONFIRM = "pending_confirm"
    RELEASED = "released"
    REVIEW_FAILED = "review_failed"


class Project(Base):
    """A development & testing project."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(255), index=True, nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pm_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
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

    # Relationships
    pm: Mapped["User"] = relationship(
        "User", back_populates="managed_projects", foreign_keys=[pm_user_id]
    )
    members: Mapped[List["ProjectMember"]] = relationship(
        "ProjectMember", back_populates="project", cascade="all, delete-orphan"
    )
    versions: Mapped[List["Version"]] = relationship(
        "Version", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    """A user belonging to a project with a specific role."""

    __tablename__ = "project_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    project_role: Mapped[ProjectRole] = mapped_column(
        SAEnum(ProjectRole, name="project_role"),
        nullable=False,
        default=ProjectRole.DEVELOPER,
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project", back_populates="members"
    )
    user: Mapped["User"] = relationship(
        "User", back_populates="project_memberships"
    )


class Version(Base):
    """A version within a project."""

    __tablename__ = "versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    version_number: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    developer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    tester_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    expert_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
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

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project", back_populates="versions"
    )
    developer: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[developer_id]
    )
    tester: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[tester_id]
    )
    expert: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[expert_id]
    )
    releases: Mapped[List["Release"]] = relationship(
        "Release", back_populates="version", cascade="all, delete-orphan"
    )
    external_recipients: Mapped[List["ExternalRecipient"]] = relationship(
        "ExternalRecipient",
        back_populates="version",
        cascade="all, delete-orphan",
    )


class Release(Base):
    """A release of a version, going through the review pipeline."""

    __tablename__ = "releases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("versions.id"), nullable=False
    )
    release_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReleaseStatus] = mapped_column(
        SAEnum(ReleaseStatus, name="release_status"),
        nullable=False,
        default=ReleaseStatus.DRAFT,
    )
    change_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    code_package_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    test_report_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    review_report_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    download_link: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True
    )
    link_expiry: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    # Relationships
    version: Mapped["Version"] = relationship(
        "Version", back_populates="releases"
    )
    confirmer: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[confirmed_by]
    )
    llm_reviews: Mapped[List["LLMReview"]] = relationship(
        "LLMReview", back_populates="release", cascade="all, delete-orphan"
    )


class ExternalRecipient(Base):
    """An external recipient for a version release link."""

    __tablename__ = "external_recipients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("versions.id"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    link_expiry_hours: Mapped[int] = mapped_column(
        Integer, default=168, nullable=False
    )
    access_scope: Mapped[str] = mapped_column(
        String(100), default="download_only", nullable=False
    )

    # Relationships
    version: Mapped["Version"] = relationship(
        "Version", back_populates="external_recipients"
    )
    user: Mapped[Optional["User"]] = relationship("User")
