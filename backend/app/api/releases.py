"""Release management API routes."""

import uuid
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import Release, ReleaseStatus, Version
from app.models.user import User
from app.schemas.project import ReleaseListResponse, ReleaseResponse
from app.services.audit_service import create_audit_log
from app.services.permission_service import check_pm_permission, check_project_access
from app.services.release_service import (
    delete_artifact,
    confirm_release,
    get_release_by_id,
    upload_code_package,
    upload_review_report,
    upload_test_report,
)
from app.storage.minio_client import minio_generate_presigned_url

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



async def _enrich_release_response(
    db: AsyncSession, release: Release, response: ReleaseResponse
) -> ReleaseResponse:
    """Populate uploader/confirmer display names on a ReleaseResponse.

    This is a post-validation step that joins the user names for display in
    the UI without forcing N+1 queries at the schema level.
    """
    from sqlalchemy import select as _select
    from app.models.user import User
    from app.models.project import Version

    # Populate project_id via version join (lazy/refresh)
    if release.version is None:
        # Refresh to load the relationship
        await db.refresh(release, ["version"])
    if release.version is not None:
        response.project_id = release.version.project_id

    user_ids = {
        response.code_package_uploaded_by,
        response.test_report_uploaded_by,
        response.review_report_uploaded_by,
        response.confirmed_by,
    }
    user_ids.discard(None)
    if not user_ids:
        return response

    result = await db.execute(_select(User).where(User.id.in_(user_ids)))
    users = {u.id: u for u in result.scalars().all()}

    if response.code_package_uploaded_by and response.code_package_uploaded_by in users:
        response.code_package_uploader_name = users[response.code_package_uploaded_by].username
    if response.test_report_uploaded_by and response.test_report_uploaded_by in users:
        response.test_report_uploader_name = users[response.test_report_uploaded_by].username
    if response.review_report_uploaded_by and response.review_report_uploaded_by in users:
        response.review_report_uploader_name = users[response.review_report_uploaded_by].username
    if response.confirmed_by and response.confirmed_by in users:
        response.confirmed_by_name = users[response.confirmed_by].username
    return response

@router.get(
    "/by-version/{version_id}",
    response_model=List[ReleaseListResponse],
)
async def list_releases_by_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all releases for a given version (newest first)."""
    result = await db.execute(
        select(Release)
        .where(Release.version_id == version_id)
        .order_by(Release.release_number.desc())
    )
    releases = result.scalars().all()
    return [ReleaseListResponse.model_validate(r) for r in releases]


@router.get("/{release_id}", response_model=ReleaseResponse)
async def get_release(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a release by ID."""
    release = await _get_release_with_project_access(db, release_id, current_user)
    response = ReleaseResponse.model_validate(release)
    return await _enrich_release_response(db, release, response)


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
        user_id=current_user.id,
    )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="upload_code_package",
        resource_type="release",
        resource_id=str(release_id),
        details={"file_name": file.filename, "change_notes": change_notes},
    )

    response = ReleaseResponse.model_validate(release)
    return await _enrich_release_response(db, release, response)


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
        user_id=current_user.id,
    )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="upload_test_report",
        resource_type="release",
        resource_id=str(release_id),
        details={"file_name": file.filename},
    )

    response = ReleaseResponse.model_validate(release)
    return await _enrich_release_response(db, release, response)


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
        user_id=current_user.id,
    )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="upload_review_report",
        resource_type="release",
        resource_id=str(release_id),
        details={"file_name": file.filename},
    )

    response = ReleaseResponse.model_validate(release)
    return await _enrich_release_response(db, release, response)


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

    response = ReleaseResponse.model_validate(release)
    return await _enrich_release_response(db, release, response)


# Mapping from URL file_type segment to the Release column storing the
# MinIO object name for that artifact.
_FILE_TYPE_TO_FIELD = {
    "code_package": "code_package_path",
    "test_report": "test_report_path",
    "review_report": "review_report_path",
}


@router.get("/{release_id}/download/{file_type}")
async def download_release_artifact(
    release_id: uuid.UUID,
    file_type: str,
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Redirect to a freshly-generated MinIO presigned URL for an artifact.

    file_type must be one of: code_package, test_report, review_report.
    The URL is short-lived (1 hour) to avoid leaking long-lived links.

    The endpoint accepts a ``token`` query parameter as a fallback to the
    Authorization header, so that browser-initiated downloads (e.g.
    ``window.open``) can still authenticate.
    """
    if file_type not in _FILE_TYPE_TO_FIELD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file_type: {file_type}",
        )

    release = await _get_release_with_project_access(
        db=db, release_id=release_id, user=current_user
    )

    object_name = getattr(release, _FILE_TYPE_TO_FIELD[file_type])
    if not object_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{file_type} not uploaded for this release",
        )

    try:
        presigned_url = minio_generate_presigned_url(
            object_name=object_name, expiry_hours=1
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate download URL: {exc}",
        )

    # Record the download in audit log (SOX: who downloaded what, when).
    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="download_artifact",
        resource_type="release",
        resource_id=str(release_id),
        details={"file_type": file_type, "object_name": object_name},
    )

    return RedirectResponse(url=presigned_url, status_code=status.HTTP_302_FOUND)



@router.delete("/{release_id}/artifacts/{file_type}", response_model=ReleaseResponse)
async def delete_release_artifact(
    release_id: uuid.UUID,
    file_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an artifact (code_package / test_report / review_report) from a release.

    Permission rules (applies only when release.status != 'released'):
    - admin / super_admin: can delete any artifact.
    - other roles: can delete only the artifact they uploaded themselves
      ( uploader_id == current_user.id ).
    """
    from app.models.user import SystemRole

    valid_types = ("code_package", "test_report", "review_report")
    if file_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file_type: {file_type}. Must be one of {valid_types}",
        )

    release = await _get_release_with_project_access(db, release_id, current_user)

    # Released releases are immutable
    if release.status == ReleaseStatus.RELEASED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete artifact: release is already released",
        )

    role = current_user.system_role
    is_admin = role in (SystemRole.ADMIN, SystemRole.SUPER_ADMIN)

    uploader_field_map = {
        "code_package": "code_package_uploaded_by",
        "test_report": "test_report_uploaded_by",
        "review_report": "review_report_uploaded_by",
    }
    path_field_map = {
        "code_package": "code_package_path",
        "test_report": "test_report_path",
        "review_report": "review_report_path",
    }

    uploader_attr = uploader_field_map[file_type]
    path_attr = path_field_map[file_type]

    if not is_admin:
        uploader_id = getattr(release, uploader_attr)
        if uploader_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete artifacts that you uploaded yourself",
            )

    if not getattr(release, path_attr):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {file_type} uploaded for this release",
        )

    try:
        updated = await delete_artifact(db=db, release_id=release_id, file_type=file_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="delete_artifact",
        resource_type="release",
        resource_id=str(release_id),
        details={
            "file_type": file_type,
            "deleted_by_role": role.value,
        },
    )

    response = ReleaseResponse.model_validate(updated)
    return await _enrich_release_response(db, updated, response)
