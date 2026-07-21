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


class ProjectMemberUpdate(BaseModel):
    """Schema for updating a project member's role."""

    project_role: ProjectRole


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
    pm_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    latest_activity_at: Optional[datetime] = None
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
    max_downloads: int = 10


class ExternalRecipientResponse(BaseModel):
    """外部接收方响应(含 access_token,功能2)。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_id: uuid.UUID
    email: str
    name: Optional[str] = None
    link_expiry_hours: int
    access_scope: str
    access_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    download_count: int = 0
    max_downloads: int = 10
    max_downloads: int = 10


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
    # 释放包完整性校验:SHA256(功能3)
    code_package_sha256: Optional[str] = None
    test_report_sha256: Optional[str] = None
    review_report_sha256: Optional[str] = None
    # Uploader info for each artifact (SOX audit traceability).
    code_package_uploaded_by: Optional[uuid.UUID] = None
    code_package_uploaded_at: Optional[datetime] = None
    test_report_uploaded_by: Optional[uuid.UUID] = None
    test_report_uploaded_at: Optional[datetime] = None
    review_report_uploaded_by: Optional[uuid.UUID] = None
    review_report_uploaded_at: Optional[datetime] = None
    # Convenience display names (populated by join).
    code_package_uploader_name: Optional[str] = None
    test_report_uploader_name: Optional[str] = None
    review_report_uploader_name: Optional[str] = None
    download_link: Optional[str] = None
    link_expiry: Optional[datetime] = None
    confirmed_by: Optional[uuid.UUID] = None
    confirmed_at: Optional[datetime] = None
    confirmed_by_name: Optional[str] = None
    # 特批放行人(功能7):PM/管理员在评审失败时强制推进的审计信息
    force_advanced_by: Optional[uuid.UUID] = None
    force_advanced_at: Optional[datetime] = None
    force_advanced_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Associated project ID (populated via version join)
    project_id: Optional[uuid.UUID] = None


class ReleaseListResponse(BaseModel):
    """Schema for release list responses with associated fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_id: uuid.UUID
    release_number: int
    status: ReleaseStatus
    change_notes: Optional[str] = None
    code_package_path: Optional[str] = None
    test_report_path: Optional[str] = None
    review_report_path: Optional[str] = None
    code_package_uploaded_by: Optional[uuid.UUID] = None
    code_package_uploaded_at: Optional[datetime] = None
    test_report_uploaded_by: Optional[uuid.UUID] = None
    test_report_uploaded_at: Optional[datetime] = None
    review_report_uploaded_by: Optional[uuid.UUID] = None
    review_report_uploaded_at: Optional[datetime] = None
    code_package_uploader_name: Optional[str] = None
    test_report_uploader_name: Optional[str] = None
    review_report_uploader_name: Optional[str] = None
    download_link: Optional[str] = None
    link_expiry: Optional[datetime] = None
    confirmed_by: Optional[uuid.UUID] = None
    confirmed_at: Optional[datetime] = None
    confirmed_by_name: Optional[str] = None
    # 特批放行人(功能7)
    force_advanced_by: Optional[uuid.UUID] = None
    force_advanced_at: Optional[datetime] = None
    force_advanced_by_name: Optional[str] = None
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
