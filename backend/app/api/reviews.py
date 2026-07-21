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

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_sse, require_roles
from app.models.project import Release, Version
from app.models.review import LLMModel, LLMReview, ReviewRule, ReviewType
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

async def _enrich_reviews_with_names(
    db: AsyncSession, reviews: list
) -> list:
    """Populate triggered_by_name on each LLMReviewResponse."""
    from sqlalchemy import select as _select
    from app.models.user import User

    user_ids = {r.triggered_by for r in reviews if r.triggered_by}
    if not user_ids:
        return reviews
    result = await db.execute(_select(User).where(User.id.in_(user_ids)))
    users = {u.id: u.username for u in result.scalars().all()}
    for r in reviews:
        if r.triggered_by and r.triggered_by in users:
            r.triggered_by_name = users[r.triggered_by]
    return reviews

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
    resp = [LLMReviewResponse.model_validate(r) for r in reviews]
    return await _enrich_reviews_with_names(db, resp)


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

    Returns 412 Precondition Failed if no active review rule is configured
    for the requested review type, so the frontend can surface a clear
    error message to the user.
    """
    release = await _get_release_and_check_access(db, release_id, current_user)

    # 锁定 release 行,防止并发触发评审
    lock_result = await db.execute(
        select(Release).where(Release.id == release_id).with_for_update()
    )
    locked_release = lock_result.scalar_one_or_none()
    if locked_release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Release not found",
        )

    # 预检:对应的 review_type 是否配置了启用的评审规则 + 启用的 LLM 模型
    # 避免触发 Celery 任务后才报错,让前端能给出明确提示
    rule_result = await db.execute(
        select(ReviewRule)
        .where(
            ReviewRule.review_type == review_type,
            ReviewRule.is_active.is_(True),
        )
    )
    review_rule = rule_result.scalar_one_or_none()
    if review_rule is None:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=(
                f"评审规则未配置:没有为「{review_type.value}」类型配置启用的评审规则。"
                "请联系管理员在 LLM 配置页的「评审规则管理」中添加。"
            ),
        )
    # 检查规则引用的 LLM 模型是否存在且启用
    model_result = await db.execute(
        select(LLMModel).where(LLMModel.id == review_rule.llm_model_id)
    )
    llm_model = model_result.scalar_one_or_none()
    if llm_model is None or not llm_model.is_active:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=(
                f"评审规则引用的 LLM 模型不可用:规则「{review_type.value}」"
                "关联的模型已删除或被禁用,请联系管理员在 LLM 配置页检查。"
            ),
        )

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


@router.get("/stream/{release_id}")
async def stream_review_progress(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_sse),
):
    """SSE 端点:推送指定 release 的最新评审进度。

    前端用 EventSource 接收,每 2 秒查询一次最新评审状态并推送;
    当评审进入终态(passed/failed/error)时关闭流。
    认证通过 query 参数 ?token=xxx 传递(EventSource 不支持自定义 header)。
    """
    async def event_generator():
        while True:
            try:
                result = await db.execute(
                    select(LLMReview)
                    .where(LLMReview.release_id == release_id)
                    .order_by(LLMReview.created_at.desc())
                    .limit(1)
                )
                review = result.scalar_one_or_none()
            except Exception as exc:  # 数据库异常不应中断流,推送错误事件后退出
                err = {"error": str(exc)}
                yield f"data: {json.dumps(err)}\n\n"
                break

            if review:
                # result 枚举转字符串,便于前端处理
                result_str = review.result.value if hasattr(review.result, "value") else str(review.result)
                review_type_str = review.review_type.value if hasattr(review.review_type, "value") else str(review.review_type)
                data = {
                    "review_id": str(review.id),
                    "result": result_str,
                    "review_type": review_type_str,
                    "review_round": review.review_round,
                    "total_score": review.total_score,
                    "conclusion": review.conclusion,
                    "suggestions": review.suggestions,
                    "model_used": review.model_used,
                    "created_at": review.created_at.isoformat() if review.created_at else None,
                    "completed_at": review.completed_at.isoformat() if review.completed_at else None,
                }
                yield f"data: {json.dumps(data)}\n\n"

                # 终态:关闭流
                if result_str in ("passed", "failed", "error"):
                    break

            # 心跳注释,保持连接
            yield ": heartbeat\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
