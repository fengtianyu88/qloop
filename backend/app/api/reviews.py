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
from app.models.review import LLMModel, LLMReview, ReviewResult, ReviewRule, ReviewType
from app.models.user import SystemRole, User
from app.redis_client import get_redis
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

    # 预检:是否已有进行中的评审(防止并发触发,API 层提前返回 409)
    pending_check = await db.execute(
        select(LLMReview).where(
            LLMReview.release_id == release.id,
            LLMReview.review_type == review_type,
            LLMReview.result == ReviewResult.PENDING,
        ).limit(1)
    )
    if pending_check.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该评审类型已有进行中的评审,请等待完成",
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
    """SSE 端点:推送指定 release 的实时评审进度。

    订阅 Redis pub/sub channel ``review_stream:{release_id}``,
    把 Celery 评审任务通过 progress_callback 推送的步骤事件(step)和
    LLM 流式 chunk 实时转发给前端 EventSource。

    启动时先查数据库:如果评审已终态则直接返回最终状态;
    否则订阅 Redis channel 等待实时事件;
    收到 done/error 终态事件后查数据库推送最终评审记录并关闭流;
    5 分钟无事件自动关闭(防泄漏)。
    """
    async def _build_review_data(review: LLMReview, evt_type: str = "done") -> dict:
        result_str = review.result.value if hasattr(review.result, "value") else str(review.result)
        review_type_str = review.review_type.value if hasattr(review.review_type, "value") else str(review.review_type)
        return {
            "type": evt_type,
            "result": result_str,
            "review_id": str(review.id),
            "review_type": review_type_str,
            "review_round": review.review_round,
            "total_score": review.total_score,
            "conclusion": review.conclusion,
            "suggestions": review.suggestions,
            "model_used": review.model_used,
        }

    async def event_generator():
        # 1. 订阅 Redis pub/sub channel (先订阅,确保不遗漏事件)
        channel = f"review_stream:{release_id}"
        try:
            redis = await get_redis()
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'payload': f'Redis 连接失败: {exc}'}, ensure_ascii=False)}\n\n"
            return

        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)

        # 2. 查 DB 获取当前评审状态
        # 如果有 PENDING 评审,等待 Redis 事件(step/chunk/done)
        # 如果没有 PENDING 评审,也不推送旧 done - 保持订阅等待新评审被触发
        # (前端通过 GET /api/reviews/release/{id} 查询历史评审记录,
        #  SSE 的职责是实时推送新事件,不负责推送历史结果)
        try:
            pending_result = await db.execute(
                select(LLMReview)
                .where(
                    LLMReview.release_id == release_id,
                    LLMReview.result == ReviewResult.PENDING,
                )
                .order_by(LLMReview.created_at.desc())
                .limit(1)
            )
            pending_review = pending_result.scalar_one_or_none()
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'payload': str(exc)}, ensure_ascii=False)}\n\n"
            return

        if pending_review is not None:
            # 有 PENDING 评审,推送 connected 事件让前端知道 SSE 已连接
            yield f"data: {json.dumps({'type': 'connected', 'payload': '评审进行中'}, ensure_ascii=False)}\n\n"
        # 没有 PENDING 评审时不推送任何东西,直接进入 Redis 订阅循环等待新事件

        idle_seconds = 0
        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    idle_seconds = 0
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield f"data: {data}\n\n"

                    # 检查是否终态事件(done/error),查数据库推送最终结果
                    try:
                        evt = json.loads(data)
                        if evt.get("type") in ("done", "error"):
                            try:
                                final_result = await db.execute(
                                    select(LLMReview)
                                    .where(LLMReview.release_id == release_id)
                                    .order_by(LLMReview.created_at.desc())
                                    .limit(1)
                                )
                                final_review = final_result.scalar_one_or_none()
                                if final_review:
                                    final_data = await _build_review_data(final_review, "final")
                                    yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"
                            except Exception:
                                pass
                            break
                    except (json.JSONDecodeError, KeyError):
                        pass
                else:
                    idle_seconds += 1
                    if idle_seconds >= 300:
                        yield f"data: {json.dumps({'type': 'timeout', 'payload': 'SSE 连接超时(5分钟无事件)'}, ensure_ascii=False)}\n\n"
                        break
                    yield ": heartbeat\n\n"
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
