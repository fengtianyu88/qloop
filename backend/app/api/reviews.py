"""Review API routes.

Exposes endpoints to:
    * List all LLM review records for a release.
    * Trigger an asynchronous LLM review for a release.

Triggering a review dispatches a Celery task and returns the task ID
immediately; the caller can poll the release / review endpoints to
observe the outcome.
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.project import Release, Version
from app.models.review import LLMReview, ReviewType
from app.models.user import SystemRole, User
from app.schemas.review import LLMReviewResponse
from app.services.audit_service import create_audit_log
from app.services.permission_service import check_project_access
from app.services.release_service import get_release_by_id

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# Roles allowed to trigger a review.
_TRIGGER_ROLES = require_roles(
    SystemRole.DEVELOPER, SystemRole.ADMIN, SystemRole.SUPER_ADMIN
)


class TriggerReviewResponse(BaseModel):
    """Response for the trigger-review endpoint."""

    task_id: str
    release_id: str
    review_type: str
    status: str = "queued"


async def _get_release_and_check_access(
    db: AsyncSession,
    release_id: uuid.UUID,
    user: User,
) -> Release:
    """Fetch a release and verify the user has access to its project.

    Raises:
        HTTPException 404: If the release or its version is not found.
        HTTPException 403: If the user lacks project access.
    """
    release = await get_release_by_id(db=db, release_id=release_id)
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )

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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/release/{release_id}",
    response_model=List[LLMReviewResponse],
)
async def list_release_reviews(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all LLM review records for a release, newest first."""
    await _get_release_and_check_access(db, release_id, current_user)

    result = await db.execute(
        select(LLMReview)
        .where(LLMReview.release_id == release_id)
        .order_by(LLMReview.created_at.desc())
    )
    reviews = result.scalars().all()
    return [LLMReviewResponse.model_validate(r) for r in reviews]


@router.post(
    "/trigger/{release_id}",
    response_model=TriggerReviewResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_review(
    release_id: uuid.UUID,
    review_type: ReviewType = Query(..., description="Type of review to trigger"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_TRIGGER_ROLES),
):
    """Trigger an asynchronous LLM review for a release.

    Allowed roles: DEVELOPER, ADMIN, SUPER_ADMIN.

    The review runs in a Celery worker; this endpoint returns immediately
    with the task ID.
    """
    release = await _get_release_and_check_access(db, release_id, current_user)

    # Import the task lazily to avoid importing Celery/Redis at module
    # import time in contexts where they may not be configured.
    from app.tasks.review_tasks import run_llm_review

    async_result = run_llm_review.delay(
        release_id=str(release.id),
        review_type=review_type.value,
        triggered_by=str(current_user.id),
    )

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="trigger_llm_review",
        resource_type="release",
        resource_id=str(release.id),
        details={
            "review_type": review_type.value,
            "task_id": async_result.id,
        },
    )

    return TriggerReviewResponse(
        task_id=async_result.id,
        release_id=str(release.id),
        review_type=review_type.value,
    )
