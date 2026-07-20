"""Release management service."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Release, ReleaseStatus
from app.storage.minio_client import (
    minio_delete_object,
    minio_generate_presigned_url,
    minio_upload_file,
)


async def get_release_by_id(
    db: AsyncSession, release_id: uuid.UUID
) -> Optional[Release]:
    """Get a release by ID with version eagerly loaded."""
    result = await db.execute(
        select(Release)
        .options(selectinload(Release.version))
        .where(Release.id == release_id)
    )
    return result.scalar_one_or_none()


async def upload_code_package(
    db: AsyncSession,
    release_id: uuid.UUID,
    file_data: bytes,
    file_name: str,
    content_type: str,
    change_notes: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None,
) -> Optional[Release]:
    """Upload a code package to MinIO and update the release status.

    Args:
        db: The async database session.
        release_id: The release ID.
        file_data: The file content as bytes.
        file_name: The original file name.
        content_type: The MIME content type.
        change_notes: Optional change notes to attach.

    Returns:
        The updated Release object, or ``None`` if not found.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    object_name = f"releases/{release_id}/code_package/{file_name}"
    minio_upload_file(object_name, file_data, len(file_data), content_type)

    release.code_package_path = object_name
    release.status = ReleaseStatus.CODE_PENDING_REVIEW
    if change_notes is not None:
        release.change_notes = change_notes
    if user_id is not None:
        release.code_package_uploaded_by = user_id
        release.code_package_uploaded_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(release)
    return release


async def upload_test_report(
    db: AsyncSession,
    release_id: uuid.UUID,
    file_data: bytes,
    file_name: str,
    content_type: str,
    user_id: Optional[uuid.UUID] = None,
) -> Optional[Release]:
    """Upload a test report to MinIO and update the release status.

    Args:
        db: The async database session.
        release_id: The release ID.
        file_data: The file content as bytes.
        file_name: The original file name.
        content_type: The MIME content type.

    Returns:
        The updated Release object, or ``None`` if not found.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    object_name = f"releases/{release_id}/test_report/{file_name}"
    minio_upload_file(object_name, file_data, len(file_data), content_type)

    release.test_report_path = object_name
    release.status = ReleaseStatus.TEST_PENDING_REVIEW
    if user_id is not None:
        release.test_report_uploaded_by = user_id
        release.test_report_uploaded_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(release)
    return release


async def upload_review_report(
    db: AsyncSession,
    release_id: uuid.UUID,
    file_data: bytes,
    file_name: str,
    content_type: str,
    user_id: Optional[uuid.UUID] = None,
) -> Optional[Release]:
    """Upload a review/expert report to MinIO and update the release status.

    Args:
        db: The async database session.
        release_id: The release ID.
        file_data: The file content as bytes.
        file_name: The original file name.
        content_type: The MIME content type.

    Returns:
        The updated Release object, or ``None`` if not found.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    object_name = f"releases/{release_id}/review_report/{file_name}"
    minio_upload_file(object_name, file_data, len(file_data), content_type)

    release.review_report_path = object_name
    release.status = ReleaseStatus.EXPERT_PENDING_REVIEW
    if user_id is not None:
        release.review_report_uploaded_by = user_id
        release.review_report_uploaded_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(release)
    return release


async def confirm_release(
    db: AsyncSession, release_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[Release]:
    """Confirm a release, setting status to RELEASED.

    Generates a presigned download link with a default 168-hour expiry.

    Args:
        db: The async database session.
        release_id: The release ID.
        user_id: The ID of the user confirming the release.

    Returns:
        The updated Release object, or ``None`` if not found.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    release.status = ReleaseStatus.RELEASED
    release.confirmed_by = user_id
    release.confirmed_at = datetime.now(timezone.utc)

    # Generate a presigned download link for the code package
    if release.code_package_path:
        try:
            download_link = minio_generate_presigned_url(
                release.code_package_path, expiry_hours=168
            )
            release.download_link = download_link
            release.link_expiry = datetime.now(timezone.utc) + timedelta(hours=168)
        except Exception:
            # If presigned URL generation fails, still mark as released
            pass

    await db.commit()
    await db.refresh(release)
    return release


async def handle_review_failure(
    db: AsyncSession, release_id: uuid.UUID
) -> Optional[Release]:
    """Handle a review failure by setting the release status to REVIEW_FAILED.

    Args:
        db: The async database session.
        release_id: The release ID.

    Returns:
        The updated Release object, or ``None`` if not found.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    release.status = ReleaseStatus.REVIEW_FAILED

    await db.commit()
    await db.refresh(release)
    return release


async def advance_release_after_review(
    db: AsyncSession, release_id: uuid.UUID
) -> Optional[Release]:
    """Advance the release status after an LLM review passes.

    Transitions:
        - CODE_PENDING_REVIEW -> TEST_PENDING_REVIEW
        - TEST_PENDING_REVIEW -> EXPERT_PENDING_REVIEW
        - EXPERT_PENDING_REVIEW -> PENDING_CONFIRM

    Args:
        db: The async database session.
        release_id: The release ID.

    Returns:
        The updated Release object, or ``None`` if not found.

    Raises:
        ValueError: If the current status does not allow advancement.
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    status_transitions = {
        ReleaseStatus.CODE_PENDING_REVIEW: ReleaseStatus.TEST_PENDING_REVIEW,
        ReleaseStatus.TEST_PENDING_REVIEW: ReleaseStatus.EXPERT_PENDING_REVIEW,
        ReleaseStatus.EXPERT_PENDING_REVIEW: ReleaseStatus.PENDING_CONFIRM,
    }

    next_status = status_transitions.get(release.status)
    if next_status is None:
        raise ValueError(
            f"Cannot advance release in status '{release.status.value}'"
        )

    release.status = next_status

    await db.commit()
    await db.refresh(release)
    return release



async def delete_artifact(
    db: AsyncSession,
    release_id: uuid.UUID,
    file_type: str,
) -> Optional[Release]:
    """Delete an artifact from MinIO and clear its fields on the release.

    Args:
        db: The async database session.
        release_id: The release ID.
        file_type: One of 'code_package', 'test_report', 'review_report'.

    Returns:
        The updated Release object, or None if release not found.

    Raises:
        ValueError: If file_type is invalid, or if the release is already
            released (released releases are immutable).
    """
    release = await get_release_by_id(db, release_id)
    if release is None:
        return None

    if release.status == ReleaseStatus.RELEASED:
        raise ValueError("Cannot delete artifact: release is already released")

    field_map = {
        "code_package": ("code_package_path", "code_package_uploaded_by", "code_package_uploaded_at"),
        "test_report": ("test_report_path", "test_report_uploaded_by", "test_report_uploaded_at"),
        "review_report": ("review_report_path", "review_report_uploaded_by", "review_report_uploaded_at"),
    }
    if file_type not in field_map:
        raise ValueError(f"Invalid file_type: {file_type}")

    path_attr, uploader_attr, uploaded_at_attr = field_map[file_type]
    object_name = getattr(release, path_attr)
    if object_name:
        try:
            minio_delete_object(object_name)
        except Exception:
            # Best-effort: log but continue to clear DB fields
            pass

    setattr(release, path_attr, None)
    setattr(release, uploader_attr, None)
    setattr(release, uploaded_at_attr, None)

    # If deleting code_package, also clear change_notes? No - change_notes may
    # be a project-level field; leave it alone.
    await db.commit()
    await db.refresh(release)
    return release
