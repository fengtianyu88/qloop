"""Organization-related Pydantic schemas."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 组织类型 v1.5.2
# ---------------------------------------------------------------------------

class OrgTypeCreate(BaseModel):
    """创建组织类型请求。"""

    code: str = Field(..., min_length=1, max_length=50, description="程序识别码(小写英文)")
    name: str = Field(..., min_length=1, max_length=100, description="显示名称")
    sort_order: int = Field(default=0, ge=0, description="排序序号")


class OrgTypeResponse(BaseModel):
    """组织类型响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    is_system: bool
    sort_order: int
    created_by: Optional[uuid.UUID] = None
    created_by_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# 组织单元
# ---------------------------------------------------------------------------

class OrgUnitCreate(BaseModel):
    """Schema for creating an organizational unit."""

    name: str
    org_type: str = "department"
    parent_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    is_active: bool = True


class OrgUnitUpdate(BaseModel):
    """Schema for updating an organizational unit."""

    name: Optional[str] = None
    org_type: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class OrgUnitResponse(BaseModel):
    """Schema for org unit responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    org_type: str
    parent_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OrgTreeResponse(BaseModel):
    """Schema for org unit tree responses (with children)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    org_type: str
    parent_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Display names of users who administer this org unit (populated by service).
    manager_names: List[str] = []
    children: List["OrgTreeResponse"] = []


# ---------------------------------------------------------------------------
# 管理员范围
# ---------------------------------------------------------------------------

class AdminScopeCreate(BaseModel):
    """Schema for creating an admin scope."""

    user_id: uuid.UUID
    org_unit_id: uuid.UUID


class AdminScopeResponse(BaseModel):
    """Schema for admin scope responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    org_unit_id: uuid.UUID


# Resolve forward reference for recursive OrgTreeResponse
OrgTreeResponse.model_rebuild()
