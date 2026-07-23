"""LLM review execution engine.

This module orchestrates a single LLM review for a release:

1. Load the release and the matching :class:`ReviewRule`.
2. Create a ``PENDING`` :class:`LLMReview` record.
3. Prepare the review content (download the relevant artifact from
   MinIO and parse it).
4. Render the prompt template and call the LLM (with fallback).
5. Parse the LLM's JSON response.
6. Update the review record with scores / conclusion / suggestions.
7. Decide pass/fail and advance (or fail) the release status.
8. Return the persisted :class:`LLMReview`.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.llm.client import (
    LLMResponse,
    call_llm_with_fallback,
    parse_llm_review_result,
)
from app.llm.code_parser import build_llm_input, parse_code_package
from app.llm.doc_parser import parse_document
from app.llm.prompts import PROMPT_MAP
from app.models.project import Release, ReleaseStatus
from app.models.review import (
    LLMModel,
    LLMReview,
    ReviewResult,
    ReviewRule,
    ReviewType,
)
from app.storage.minio_client import minio_download_file

logger = logging.getLogger(__name__)


# Mapping of (review_type -> status when the review passes).
_PASS_STATUS_TRANSITIONS = {
    ReviewType.CODE_REVIEW: ReleaseStatus.TEST_PENDING_REVIEW,
    ReviewType.TEST_REPORT_REVIEW: ReleaseStatus.EXPERT_PENDING_REVIEW,
    ReviewType.EXPERT_REPORT_REVIEW: ReleaseStatus.PENDING_CONFIRM,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_release(db: AsyncSession, release_id: uuid.UUID) -> Release:
    """Fetch a release by ID or raise ``ValueError`` if not found."""
    result = await db.execute(
        select(Release).where(Release.id == release_id)
    )
    release = result.scalar_one_or_none()
    if release is None:
        raise ValueError(f"Release {release_id} not found")
    return release


async def _get_review_rule(
    db: AsyncSession, review_type: ReviewType
) -> ReviewRule:
    """Fetch the active review rule for a review type.

    Eagerly loads the primary and fallback LLM models so they can be used
    without additional lazy queries after the session might be closed.

    Raises:
        ValueError: If no active rule is configured for the review type.
    """
    result = await db.execute(
        select(ReviewRule)
        .options(
            selectinload(ReviewRule.llm_model),
            selectinload(ReviewRule.fallback_model),
        )
        .where(
            ReviewRule.review_type == review_type,
            ReviewRule.is_active.is_(True),
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise ValueError(
            f"No active review rule configured for review type "
            f"'{review_type.value}'"
        )
    if rule.llm_model is None or not rule.llm_model.is_active:
        raise ValueError(
            f"Review rule for '{review_type.value}' has no active primary "
            f"LLM model"
        )
    return rule


async def _next_review_round(
    db: AsyncSession, release_id: uuid.UUID, review_type: ReviewType
) -> int:
    """Compute the next review round number for a release + review type."""
    result = await db.execute(
        select(func.max(LLMReview.review_round)).where(
            LLMReview.release_id == release_id,
            LLMReview.review_type == review_type,
        )
    )
    current_max = result.scalar()
    return (current_max or 0) + 1


def _basename_from_path(path: Optional[str]) -> str:
    """Return the basename of a MinIO object path, or a fallback name."""
    if not path:
        return "document"
    return os.path.basename(path) or "document"


# ---------------------------------------------------------------------------
# Content preparation
# ---------------------------------------------------------------------------
async def _prepare_review_content(
    release: Release, review_type: ReviewType
) -> str:
    """Download and parse the artifact required for a review type.

    Args:
        release: The release being reviewed.
        review_type: The type of review being performed.

    Returns:
        The plain-text content to embed in the LLM prompt.

    Raises:
        ValueError: If the required artifact has not been uploaded.
    """
    if review_type == ReviewType.CODE_REVIEW:
        if not release.code_package_path:
            raise ValueError(
                "Code package has not been uploaded for this release"
            )
        file_data = minio_download_file(release.code_package_path)
        summary = parse_code_package(file_data)
        return build_llm_input(summary, release.change_notes or "")

    if review_type == ReviewType.TEST_REPORT_REVIEW:
        if not release.test_report_path:
            raise ValueError(
                "Test report has not been uploaded for this release"
            )
        file_data = minio_download_file(release.test_report_path)
        return parse_document(
            file_data, _basename_from_path(release.test_report_path)
        )

    if review_type == ReviewType.EXPERT_REPORT_REVIEW:
        if not release.review_report_path:
            raise ValueError(
                "Expert review report has not been uploaded for this release"
            )
        file_data = minio_download_file(release.review_report_path)
        return parse_document(
            file_data, _basename_from_path(release.review_report_path)
        )

    raise ValueError(f"Unknown review type: {review_type}")


# ---------------------------------------------------------------------------
# Pass / fail evaluation
# ---------------------------------------------------------------------------
def _check_pass(parsed: dict, rule: ReviewRule) -> bool:
    """Decide whether a parsed review result passes the rule.

    A review passes only if **all** of the following hold:
        * The parsed ``conclusion`` is not ``"failed"``.
        * The ``total_score`` is at least ``rule.pass_threshold``.
        * Every dimension listed in ``rule.dimension_thresholds`` has a
          score in ``parsed["dimension_scores"]`` that meets or exceeds
          the configured threshold.

    Args:
        parsed: The dict returned by :func:`parse_llm_review_result`.
        rule: The applicable :class:`ReviewRule`.

    Returns:
        ``True`` if the review passes, ``False`` otherwise.
    """
    conclusion = str(parsed.get("conclusion", "")).strip().lower()
    if conclusion == "failed":
        return False

    total_score = parsed.get("total_score", 0)
    try:
        total_score = float(total_score)
    except (TypeError, ValueError):
        total_score = 0.0
    if total_score < float(rule.pass_threshold):
        return False

    dimension_scores = parsed.get("dimension_scores") or {}
    if not isinstance(dimension_scores, dict):
        dimension_scores = {}
    thresholds = rule.dimension_thresholds or {}
    if not isinstance(thresholds, dict):
        thresholds = {}

    for dim_name, threshold in thresholds.items():
        try:
            threshold_value = float(threshold)
        except (TypeError, ValueError):
            continue
        score = dimension_scores.get(dim_name)
        try:
            score = float(score)
        except (TypeError, ValueError):
            # Required dimension missing or non-numeric -> fail.
            return False
        if score < threshold_value:
            return False

    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def execute_review(
    db: AsyncSession,
    release_id: uuid.UUID,
    review_type: ReviewType,
    triggered_by: uuid.UUID,
    progress_callback=None,
) -> LLMReview:
    """Execute a single LLM review for a release.

    This function performs the full review lifecycle described in the
    module docstring. It is designed to be invoked from a Celery task
    using a dedicated database session.

    Args:
        db: An open async database session.
        release_id: The release to review.
        review_type: The type of review to perform.
        triggered_by: The user ID that triggered the review.

    Returns:
        The persisted :class:`LLMReview` record (with final result, score
        and conclusion populated).
    """
    # 1. Load the release.
    release = await _get_release(db, release_id)

    # 2. Load the review rule (with primary + fallback models).
    rule = await _get_review_rule(db, review_type)

    # 在创建新 PENDING 评审前,检查是否已有 PENDING 评审(防止并发触发)
    existing_pending = await db.execute(
        select(LLMReview).where(
            LLMReview.release_id == release_id,
            LLMReview.review_type == review_type,
            LLMReview.result == ReviewResult.PENDING,
        )
    )
    if existing_pending.scalar_one_or_none():
        raise ValueError("该评审类型已有进行中的评审,请等待完成")

    # 3. Create the PENDING review record.
    review_round = await _next_review_round(db, release_id, review_type)
    review = LLMReview(
        release_id=release_id,
        review_type=review_type,
        review_round=review_round,
        result=ReviewResult.PENDING,
        triggered_by=triggered_by,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    async def _emit(event_type: str, payload: str) -> None:
        """通过 progress_callback 推送步骤事件到 Redis pub/sub → SSE → 前端。"""
        if progress_callback:
            try:
                await progress_callback(event_type, payload)
            except Exception:  # noqa: BLE001
                pass

    try:
        # 4. Prepare the review content.
        await _emit("step", "读取交付物文件...")
        content = await _prepare_review_content(release, review_type)
        await _emit("step", f"读取文件成功(共 {len(content)} 字符)")

        # 5. Render the prompt.
        await _emit("step", "渲染评审提示词...")
        prompt_template = rule.prompt_template or PROMPT_MAP.get(review_type.value, "")
        if not prompt_template:
            raise ValueError(
                f"No prompt template available for review type "
                f"'{review_type.value}'"
            )
        prompt = prompt_template.replace("{content}", content)
        await _emit("step", "提示词准备完成")

        # 6. Call the LLM (primary + optional fallback).
        fallback_model: Optional[LLMModel] = rule.fallback_model
        if fallback_model is not None and not fallback_model.is_active:
            fallback_model = None
        model_name = rule.llm_model.model_name if rule.llm_model else "未知"
        await _emit("step", f"连接 LLM({model_name})...")
        await _emit("step", "LLM 连接成功,等待流式返回...")
        # v1.5.3: 记录 LLM 调用耗时(成本追踪)
        t0 = time.perf_counter()
        llm_response: LLMResponse = await call_llm_with_fallback(
            primary_model=rule.llm_model,
            fallback_model=fallback_model,
            prompt=prompt,
            progress_callback=progress_callback,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if llm_response.success:
            await _emit("step", f"LLM 返回成功({llm_response.model_used}, {len(llm_response.content or '')} 字符)")
        else:
            await _emit("step", f"LLM 调用失败: {llm_response.error}")

        # 7. Parse the result.
        await _emit("step", "解析评审结果...")
        parsed = parse_llm_review_result(
            llm_response.content if llm_response.success else None
        )
        await _emit("step", "解析完成")

        # 8. Update the review record.
        review.total_score = float(parsed.get("total_score", 0) or 0)
        review.dimension_scores = parsed.get("dimension_scores") or {}
        # v1.5.3: 若 LLM 输出因 max_tokens 被截断,在 conclusion 中追加标注
        conclusion = parsed.get("conclusion") or ""
        if llm_response.truncated:
            truncation_note = "[注意: LLM输出因max_tokens限制被截断，结果可能不完整]"
            conclusion = f"{conclusion}\n\n{truncation_note}" if conclusion else truncation_note
        review.conclusion = conclusion
        review.suggestions = parsed.get("suggestions")
        review.risk_points = parsed.get("risk_points")
        review.model_used = llm_response.model_used
        review.raw_response = llm_response.content
        # v1.5.3: 写入成本追踪字段
        review.prompt_tokens = llm_response.prompt_tokens
        review.completion_tokens = llm_response.completion_tokens
        review.latency_ms = latency_ms
        review.completed_at = datetime.now(timezone.utc)

        # 9. Decide pass / fail.
        passed = _check_pass(parsed, rule) and llm_response.success

        if passed:
            review.result = ReviewResult.PASSED
            await _emit("step", f"评审通过!总分: {review.total_score}")
            # 10a. Advance the release status.
            next_status = _PASS_STATUS_TRANSITIONS.get(review_type)
            if next_status is not None:
                release.status = next_status
        else:
            review.result = ReviewResult.FAILED
            await _emit("step", f"评审未通过,总分: {review.total_score}")
            # 10b. Fail the release.
            release.status = ReleaseStatus.REVIEW_FAILED

        await db.commit()
        await db.refresh(review)
        return review

    except Exception as exc:  # noqa: BLE001 - record failure on the review
        logger.exception(
            "Review %s for release %s failed: %s",
            review_type.value,
            release_id,
            exc,
        )
        # Record the error on the review and fail the release.
        review.result = ReviewResult.ERROR
        review.conclusion = "failed"
        review.suggestions = f"评审执行过程中发生错误: {exc}"
        review.risk_points = "评审引擎异常，请检查日志或重试。"
        review.completed_at = datetime.now(timezone.utc)
        release.status = ReleaseStatus.REVIEW_FAILED
        try:
            await db.commit()
            await db.refresh(review)
        except Exception:  # noqa: BLE001
            await db.rollback()
        return review
