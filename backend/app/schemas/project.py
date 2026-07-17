"""Project-related Pydantic schemas."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.project import (
    ProjectRole,
    ReleaseStatus,
)


class ProjectMemberCreate(BaseModel):
    """Schema for adding a project member."""

    user_id: uuid.UUID
    project_role: ProjectRole = ProjectRole.DEVELOPER


class ProjectMemberResponse(BaseModel):
    """Schema for project member responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    project_role: ProjectRole


class ProjectCreate(BaseModel):
    """Schema for creating a project."""

    name: str
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    """Schema for project responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    pm_user_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    members: List[ProjectMemberResponse] = []


class VersionCreate(BaseModel):
    """Schema for creating a version."""

    version_number: str
    description: Optional[str] = None
    developer_id: Optional[uuid.UUID] = None
    tester_id: Optional[uuid.UUID] = None
    expert_id: Optional[uuid.UUID] = None


class VersionResponse(BaseModel):
    """Schema for version responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    version_number: str
    description: Optional[str] = None
    developer_id: Optional[uuid.UUID] = None
    tester_id: Optional[uuid.UUID] = None
    expert_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class ExternalRecipientCreate(BaseModel):
    """Schema for creating an external recipient."""

    version_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    email: str
    name: Optional[str] = None
    link_expiry_hours: int = 168
    access_scope: str = "download_only"


class ReleaseResponse(BaseModel):
    """Schema for release detail responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_id: uuid.UUID
    release_number: int
    status: ReleaseStatus
    change_notes: Optional[str] = None
    code_package_path: Optional[str] = None
    test_report_path: Optional[str] = None
    review_report_path: Optional[str] = None
    download_link: Optional[str] = None
    link_expiry: Optional[datetime] = None
    confirmed_by: Optional[uuid.UUID] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ReleaseListResponse(BaseModel):
    """Schema for release list responses with associated fields."""

    id: uuid.UUID
    version_id: uuid.UUID
    release_number: int
    status: ReleaseStatus
    change_notes: Optional[str] = None
    code_package_path: Optional[str] = None
    test_report_path: Optional[str] = None
    review_report_path: Optional[str] = None
    download_link: Optional[str] = None
    link_expiry: Optional[datetime] = None
    confirmed_by: Optional[uuid.UUID] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Associated fields from joins
    project_id: Optional[uuid.UUID] = None
    project_name: Optional[str] = None
    version_number: Optional[str] = None
    developer_id: Optional[uuid.UUID] = None
    developer_name: Optional[str] = None
    tester_id: Optional[uuid.UUID] = None
    tester_name: Optional[str] = None
    expert_id: Optional[uuid.UUID] = None
    expert_name: Optional[str] = None
