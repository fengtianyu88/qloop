"""Celery task that runs an LLM review asynchronously.

The review engine (:func:`app.llm.reviewer.execute_review`) is async and
uses an async SQLAlchemy session. Celery tasks are synchronous, so each
task creates a brand new event loop and runs the coroutine to completion
inside it.

IMPORTANT: A fresh async engine with ``NullPool`` is created per task
invocation. The globally-shared engine in ``app.database`` binds its
connection pool to whatever event loop first uses it, which is
incompatible with Celery's prefork model — reusing that engine inside a
task-created event loop raises
``RuntimeError: ... attached to a different loop``. ``NullPool`` avoids
the issue by opening a brand new database connection each time and never
pooling it across loops.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings
from app.llm.reviewer import execute_review
from app.models.notification import NotificationType
from app.models.project import Project, Release, Version
from app.models.review import LLMReview, ReviewResult, ReviewType
from app.redis_client import get_redis
from app.services.notification_service import create_notification
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run a coroutine in a dedicated event loop and return its result.

    A fresh event loop is created for each task invocation so the task is
    safe to run inside Celery's prefork pool (where the loop cannot be
    shared across worker processes).
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_session_factory() -> "async_sessionmaker[AsyncSession]":
    """Build a single-use async session factory bound to a NullPool engine.

    ``NullPool`` means every session opens a fresh DB connection that lives
    only for the duration of the current event loop, eliminating any
    cross-loop binding issues with asyncpg.
    """
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def _mark_pending_reviews_as_error(release_id: uuid.UUID, reason: str) -> None:
    """P2-3: 把指定 release 的 PENDING 评审改为 ERROR,避免任务超时后悬挂。

    在 Celery 软超时或异常路径中调用,保证界面不会停留在"评审中"状态。
    """
    session_factory = _make_session_factory()
    async with session_factory() as db:
        result = await db.execute(
            select(LLMReview).where(
                LLMReview.release_id == release_id,
                LLMReview.result == ReviewResult.PENDING,
            )
        )
        review = result.scalar_one_or_none()
        if review is not None:
            review.result = ReviewResult.ERROR
            review.conclusion = reason
            await db.commit()


# 评审类型 -> 中文标签(用于通知标题)
_REVIEW_TYPE_LABELS = {
    ReviewType.CODE_REVIEW: "代码",
    ReviewType.TEST_REPORT_REVIEW: "测试报告",
    ReviewType.EXPERT_REPORT_REVIEW: "专家报告",
}


async def _notify_after_review(
    db: AsyncSession, review: LLMReview, review_type: ReviewType
) -> None:
    """评审完成后发送通知。

    - 评审通过(PASSED):通知下一角色 YOUR_TURN。
    - 评审失败/错误(FAILED/ERROR):通知 PM REVIEW_FAILED。
    通知失败不影响评审主流程(调用方已用 try/except 包裹)。
    """
    # 查询 release -> version -> project,获取版本号与各角色 user_id
    result = await db.execute(
        select(Version, Project.pm_user_id)
        .join(Release, Release.version_id == Version.id)
        .join(Project, Project.id == Version.project_id)
        .where(Release.id == review.release_id)
    )
    row = result.first()
    if row is None:
        return
    ver, pm_user_id = row
    version_no = ver.version_number
    link_url = f"/releases/{review.release_id}"
    label = _REVIEW_TYPE_LABELS.get(review_type, review_type.value)

    if review.result == ReviewResult.PASSED:
        # 评审通过:通知下一角色
        # CODE_REVIEW -> tester;TEST_REPORT_REVIEW -> expert;EXPERT_REPORT_REVIEW -> PM
        next_role_map = {
            ReviewType.CODE_REVIEW: ver.tester_id,
            ReviewType.TEST_REPORT_REVIEW: ver.expert_id,
            ReviewType.EXPERT_REPORT_REVIEW: pm_user_id,
        }
        next_user_id = next_role_map.get(review_type)
        if next_user_id is not None:
            await create_notification(
                db, next_user_id, NotificationType.YOUR_TURN,
                f"{label}评审通过",
                f"{version_no} {label}评审已通过，轮到你操作",
                link_url,
            )
    elif review.result in (ReviewResult.FAILED, ReviewResult.ERROR):
        # 评审未通过:通知 PM 处理(可特批放行或等待重新上传)
        if pm_user_id is not None:
            await create_notification(
                db, pm_user_id, NotificationType.REVIEW_FAILED,
                f"{label}评审未通过",
                f"{version_no} {label}评审未通过，请处理（可特批放行或等待重新上传）",
                link_url,
            )


@celery_app.task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    name="run_llm_review",
)
def run_llm_review(
    self,
    release_id: str,
    review_type: str,
    triggered_by: str,
) -> dict:
    """Trigger and execute an LLM review for a release.

    Args:
        release_id: The release ID (as a string UUID).
        review_type: One of the :class:`ReviewType` values (e.g.
            ``"code_review"``).
        triggered_by: The user ID that triggered the review (string UUID).

    Returns:
        A dict with ``review_id`` (str), ``result`` (the review result
        value, e.g. ``"passed"``/``"failed"``) and ``total_score`` (float).
    """
    release_uuid = uuid.UUID(release_id)
    triggered_by_uuid = uuid.UUID(triggered_by)

    try:
        rt = ReviewType(review_type)
    except ValueError as exc:
        logger.error("Unknown review_type '%s': %s", review_type, exc)
        return {
            "review_id": None,
            "result": "error",
            "total_score": 0.0,
            "error": f"Unknown review_type: {review_type}",
        }

    session_factory = _make_session_factory()
    stream_channel = f"review_stream:{release_id}"

    async def _publish_event(event: dict) -> None:
        """通过 Redis pub/sub 把评审事件推送到 SSE 端点订阅的 channel。

        推送失败不影响评审主流程,仅记录 debug 日志。
        """
        try:
            redis = await get_redis()
            await redis.publish(
                stream_channel,
                json.dumps(event, ensure_ascii=False),
            )
        except Exception:  # noqa: BLE001
            logger.debug("publish event failed", exc_info=True)

    async def _progress_callback(event_type: str, payload: str) -> None:
        """传给 execute_review 的进度回调,把 LLM 流式 chunk 推到 Redis。"""
        await _publish_event({"type": event_type, "payload": payload})

    async def _run() -> dict:
        try:
            async with session_factory() as db:
                review = await execute_review(
                    db=db,
                    release_id=release_uuid,
                    review_type=rt,
                    triggered_by=triggered_by_uuid,
                    progress_callback=_progress_callback,
                )
                # 评审完成后通知相关角色(通知系统)
                # 通过:通知下一角色;失败/错误:通知 PM
                try:
                    await _notify_after_review(db, review, rt)
                except Exception:  # noqa: BLE001
                    logger.debug("评审后通知发送失败", exc_info=True)
            # 推送完成事件,前端据此切换到最终状态
            await _publish_event({
                "type": "done",
                "result": review.result.value if review.result else "unknown",
                "review_id": str(review.id),
                "total_score": float(review.total_score or 0.0),
            })
            return {
                "review_id": str(review.id),
                "result": review.result.value if review.result else "unknown",
                "total_score": float(review.total_score or 0.0),
            }
        except Exception as exc:
            # 推送错误事件,前端 SSE 据此显示失败并关闭流
            await _publish_event({
                "type": "error",
                "payload": str(exc),
            })
            raise

    try:
        return _run_async(_run())
    except SoftTimeLimitExceeded:
        # P2-3: Celery 软超时(默认 540s),把 PENDING 评审改为 ERROR 并记录
        logger.error("LLM 评审任务软超时 release_id=%s", release_id)
        # 推送超时事件给前端 SSE
        try:
            _run_async(_publish_event({
                "type": "error",
                "payload": "评审任务超时(SoftTimeLimitExceeded)",
            }))
        except Exception as publish_err:  # noqa: BLE001
            logger.debug("publish timeout error failed: %s", publish_err)
        try:
            _run_async(_mark_pending_reviews_as_error(release_uuid, "评审任务超时"))
        except Exception as mark_err:  # noqa: BLE001
            logger.warning("标记 PENDING 为 ERROR 失败: %s", mark_err)
        return {
            "review_id": None,
            "result": "error",
            "total_score": 0.0,
            "error": "评审任务超时(SoftTimeLimitExceeded)",
        }
    except (ConnectionError, TimeoutError, OSError) as exc:
        # 连接类异常自动重试(最多 3 次,间隔 60 秒)
        logger.warning("run_llm_review 连接异常,将重试: %s", exc)
        raise self.retry(exc=exc, countdown=60)
    except Exception as exc:  # noqa: BLE001
        # LLM 评审本身失败不重试,仅记录错误
        logger.exception("run_llm_review failed: %s", exc)
        # 推送错误事件给前端 SSE(注意:_run() 内部已经推送过,
        # 这里兜底处理 _run() 外部的异常,例如 _run_async 本身的异常)
        try:
            _run_async(_publish_event({
                "type": "error",
                "payload": f"run_llm_review failed: {exc}",
            }))
        except Exception as publish_err:  # noqa: BLE001
            logger.debug("publish outer error failed: %s", publish_err)
        # P2-3: 同步把可能残留的 PENDING 评审改为 ERROR
        try:
            _run_async(_mark_pending_reviews_as_error(release_uuid, str(exc)))
        except Exception as mark_err:  # noqa: BLE001
            logger.warning("标记 PENDING 为 ERROR 失败: %s", mark_err)
        return {
            "review_id": None,
            "result": "error",
            "total_score": 0.0,
            "error": str(exc),
        }
