"""Organization-related Pydantic schemas."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.organization import OrgType


class OrgUnitCreate(BaseModel):
    """Schema for creating an organizational unit."""

    name: str
    org_type: OrgType = OrgType.DEPARTMENT
    parent_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    is_active: bool = True


class OrgUnitUpdate(BaseModel):
    """Schema for updating an organizational unit."""

    name: Optional[str] = None
    org_type: Optional[OrgType] = None
    parent_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class OrgUnitResponse(BaseModel):
    """Schema for org unit responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    org_type: OrgType
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
    org_type: OrgType
    parent_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Display names of users who administer this org unit (populated by service).
    manager_names: List[str] = []
    children: List["OrgTreeResponse"] = []


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
