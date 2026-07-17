"""Release management API routes."""

import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import Release, Version
from app.models.user import User
from app.schemas.project import ReleaseResponse
from app.services.audit_service import create_audit_log
from app.services.permission_service import check_pm_permission, check_project_access
from app.services.release_service import (
    confirm_release,
    get_release_by_id,
    upload_code_package,
    upload_review_report,
    upload_test_report,
)

router = APIRouter(prefix="/api/releases", tags=["releases"])


async def _get_release_with_project_access(
    db: AsyncSession,
    release_id: uuid.UUID,
    user: User,
) -> Release:
    """Get a release and verify the user has project access.

    Raises:
        HTTPException 404: If the release is not found.
        HTTPException 403: If the user lacks project access.
    """
    release = await get_release_by_id(db=db, release_id=release_id)
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )

    # Get the version to find the project_id
    version_result = await db.execute(
        select(Version).where(Version.id == release.version_id)
    )
    version = version_result.scalar_one_or_none()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated version not found",
        )

    has_access = await check_project_access(db, user, version.project_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this release's project",
        )

    return release


@router.get("/{release_id}", response_model=ReleaseResponse)
async def get_release(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a release by ID."""
    release = await _get_release_with_project_access(db, release_id, current_user)
    return ReleaseResponse.model_validate(release)


@router.post("/{release_id}/code-package", response_model=ReleaseResponse)
async def upload_code_package_endpoint(
    release_id: uuid.UUID,
    file: UploadFile = File(...),
    change_notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a code package for a release.

    The file is stored in MinIO and the release status is updated to
    ``CODE_PENDING_REVIEW``.
    """
    release = await _get_release_with_project_access(db, release_id, current_user)

    file_data = await file.read()
    content_type = file.content_type or "application/octet-stream"

    release = await upload_code_package(
        db=db,
        release_id=release_id,
        file_data=file_data,
        file_name=file.filename or "code_package",
        content_type=content_type,
        change_notes=change_notes,
    )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="upload_code_package",
        resource_type="release",
        resource_id=str(release_id),
        details={"file_name": file.filename, "change_notes": change_notes},
    )

    return ReleaseResponse.model_validate(release)


@router.post("/{release_id}/test-report", response_model=ReleaseResponse)
async def upload_test_report_endpoint(
    release_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a test report for a release.

    The file is stored in MinIO and the release status is updated to
    ``TEST_PENDING_REVIEW``.
    """
    release = await _get_release_with_project_access(db, release_id, current_user)

    file_data = await file.read()
    content_type = file.content_type or "application/octet-stream"

    release = await upload_test_report(
        db=db,
        release_id=release_id,
        file_data=file_data,
        file_name=file.filename or "test_report",
        content_type=content_type,
    )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="upload_test_report",
        resource_type="release",
        resource_id=str(release_id),
        details={"file_name": file.filename},
    )

    return ReleaseResponse.model_validate(release)


@router.post("/{release_id}/review-report", response_model=ReleaseResponse)
async def upload_review_report_endpoint(
    release_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a review/expert report for a release.

    The file is stored in MinIO and the release status is updated to
    ``EXPERT_PENDING_REVIEW``.
    """
    release = await _get_release_with_project_access(db, release_id, current_user)

    file_data = await file.read()
    content_type = file.content_type or "application/octet-stream"

    release = await upload_review_report(
        db=db,
        release_id=release_id,
        file_data=file_data,
        file_name=file.filename or "review_report",
        content_type=content_type,
    )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="upload_review_report",
        resource_type="release",
        resource_id=str(release_id),
        details={"file_name": file.filename},
    )

    return ReleaseResponse.model_validate(release)


@router.post("/{release_id}/confirm", response_model=ReleaseResponse)
async def confirm_release_endpoint(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm a release, setting its status to RELEASED (PM only)."""
    release = await get_release_by_id(db=db, release_id=release_id)
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )

    # Get the version to find the project_id
    version_result = await db.execute(
        select(Version).where(Version.id == release.version_id)
    )
    version = version_result.scalar_one_or_none()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated version not found",
        )

    # Check PM permission
    is_pm = await check_pm_permission(db, current_user, version.project_id)
    if not is_pm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project manager can confirm a release",
        )

    release = await confirm_release(
        db=db, release_id=release_id, user_id=current_user.id
    )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="confirm_release",
        resource_type="release",
        resource_id=str(release_id),
        details={"status": release.status.value},
    )

    return ReleaseResponse.model_validate(release)
