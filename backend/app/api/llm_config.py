"""LLM configuration API routes.

All endpoints are restricted to ``SUPER_ADMIN`` users. They manage the
LLM model configurations and the review rules that drive the automated
review pipeline.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import require_roles
from app.models.review import LLMModel, LLMProtocol, ReviewRule, ReviewType
from app.models.user import SystemRole, User
from app.schemas.review import (
    LLMModelCreate,
    LLMModelResponse,
    ReviewRuleCreate,
    ReviewRuleResponse,
)
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/api/llm-config", tags=["llm-config"])

_SUPER_ADMIN = require_roles(SystemRole.SUPER_ADMIN)


# ---------------------------------------------------------------------------
# Update schemas (all fields optional)
# ---------------------------------------------------------------------------
class LLMModelUpdate(BaseModel):
    """Schema for partially updating an LLM model."""

    name: Optional[str] = None
    protocol: Optional[LLMProtocol] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


class ReviewRuleUpdate(BaseModel):
    """Schema for partially updating a review rule."""

    llm_model_id: Optional[uuid.UUID] = None
    fallback_model_id: Optional[uuid.UUID] = None
    prompt_template: Optional[str] = None
    pass_threshold: Optional[float] = None
    dimension_thresholds: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# LLM Models
# ---------------------------------------------------------------------------
@router.get(
    "/models",
    response_model=List[LLMModelResponse],
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def list_llm_models(
    db: AsyncSession = Depends(get_db),
):
    """List all LLM model configurations (SUPER_ADMIN only)."""
    result = await db.execute(
        select(LLMModel).order_by(LLMModel.priority.desc(), LLMModel.created_at)
    )
    return [LLMModelResponse.model_validate(m) for m in result.scalars().all()]


@router.post(
    "/models",
    response_model=LLMModelResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def create_llm_model(
    payload: LLMModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_SUPER_ADMIN),
):
    """Create a new LLM model configuration (SUPER_ADMIN only)."""
    model = LLMModel(
        name=payload.name,
        protocol=payload.protocol,
        api_base=payload.api_base,
        api_key=payload.api_key,
        model_name=payload.model_name,
        is_active=payload.is_active,
        priority=payload.priority,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="create_llm_model",
        resource_type="llm_model",
        resource_id=str(model.id),
        details={"name": model.name, "model_name": model.model_name},
    )

    return LLMModelResponse.model_validate(model)


@router.put(
    "/models/{model_id}",
    response_model=LLMModelResponse,
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def update_llm_model(
    model_id: uuid.UUID,
    payload: LLMModelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_SUPER_ADMIN),
):
    """Update an LLM model configuration (SUPER_ADMIN only)."""
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM model not found",
        )

    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(model, field_name, value)

    await db.commit()
    await db.refresh(model)

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="update_llm_model",
        resource_type="llm_model",
        resource_id=str(model.id),
        details=updates,
    )

    return LLMModelResponse.model_validate(model)


@router.post(
    "/models/{model_id}/disable",
    response_model=LLMModelResponse,
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def disable_llm_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_SUPER_ADMIN),
):
    """Disable an LLM model (soft delete) (SUPER_ADMIN only).

    The model is not physically removed; ``is_active`` is set to ``False``
    so historical review records remain referentially intact.
    """
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM model not found",
        )

    model.is_active = False
    await db.commit()
    await db.refresh(model)

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="disable_llm_model",
        resource_type="llm_model",
        resource_id=str(model.id),
        details={"is_active": False},
    )

    return LLMModelResponse.model_validate(model)


@router.post(
    "/models/{model_id}/enable",
    response_model=LLMModelResponse,
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def enable_llm_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_SUPER_ADMIN),
):
    """Re-enable a previously disabled LLM model (SUPER_ADMIN only)."""
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM model not found",
        )

    model.is_active = True
    await db.commit()
    await db.refresh(model)

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="enable_llm_model",
        resource_type="llm_model",
        resource_id=str(model.id),
        details={"is_active": True},
    )

    return LLMModelResponse.model_validate(model)


@router.delete(
    "/models/{model_id}",
    response_model=dict,
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def delete_llm_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_SUPER_ADMIN),
):
    """Physically delete an LLM model (SUPER_ADMIN only).

    Refuses if the model is still referenced by any review rule.
    Historical LLMReview records are preserved because ``model_used``
    is a free-form string, not a foreign key.
    """
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM model not found",
        )

    # Check if referenced by any review rule (as llm_model or fallback_model)
    rules_result = await db.execute(
        select(ReviewRule).where(
            (ReviewRule.llm_model_id == model_id)
            | (ReviewRule.fallback_model_id == model_id)
        )
    )
    referenced_rules = rules_result.scalars().all()
    if referenced_rules:
        rule_ids = [str(r.id) for r in referenced_rules]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot delete model '{model.name}' because it is referenced by "
                f"{len(referenced_rules)} review rule(s): {rule_ids}. "
                "Please reassign or delete those rules first."
            ),
        )

    # Snapshot for audit log
    snapshot = {"id": str(model.id), "name": model.name, "model_name": model.model_name}

    await db.delete(model)
    await db.commit()

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="delete_llm_model",
        resource_type="llm_model",
        resource_id=str(model_id),
        details=snapshot,
    )

    return {"deleted": True, "id": str(model_id), "name": snapshot["name"]}


# ---------------------------------------------------------------------------
# Model connectivity test
# ---------------------------------------------------------------------------
class LLMTestResult(BaseModel):
    """Result of an LLM model connectivity test."""

    success: bool
    message: str
    model_used: Optional[str] = None
    latency_ms: Optional[int] = None


@router.post(
    "/models/{model_id}/test",
    response_model=LLMTestResult,
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def test_llm_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Test an LLM model configuration by sending a tiny prompt.

    Returns success=True only if the endpoint responds with a parseable
    message. Otherwise success=False with the error message.
    """
    import time
    from app.llm.client import call_llm

    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM model not found",
        )

    start = time.perf_counter()
    try:
        # Use a real prompt that requires the model to return a meaningful
        # response. This verifies the API endpoint, auth, model name, and
        # the full request/response pipeline — not just network connectivity.
        test_prompt = "请回复「OK,连通测试成功」这 8 个字,不要回复其他任何内容。"
        response = await call_llm(model, test_prompt, timeout=20)
    except Exception as exc:  # pragma: no cover - defensive
        elapsed = int((time.perf_counter() - start) * 1000)
        return LLMTestResult(
            success=False,
            message=f"调用异常: {exc}",
            model_used=model.model_name,
            latency_ms=elapsed,
        )
    elapsed = int((time.perf_counter() - start) * 1000)

    if response.success:
        snippet = (response.content or "").strip().replace(chr(10), " ")
        if len(snippet) > 120:
            snippet = snippet[:120] + "…"
        if not snippet:
            return LLMTestResult(
                success=False,
                message="API 返回了空内容,请检查模型名或 API 地址是否正确",
                model_used=response.model_used,
                latency_ms=elapsed,
            )
        return LLMTestResult(
            success=True,
            message=f"连通正常,API 已成功返回结果。模型回复: {snippet}",
            model_used=response.model_used,
            latency_ms=elapsed,
        )
    return LLMTestResult(
        success=False,
        message=response.error or "调用失败",
        model_used=response.model_used,
        latency_ms=elapsed,
    )


@router.post(
    "/models/test-inline",
    response_model=LLMTestResult,
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def test_llm_model_inline(
    payload: "LLMModelCreate",
):
    """Test an LLM model configuration **before** saving it.

    Accepts the same payload as ``POST /models`` and constructs an
    in-memory ``LLMModel`` instance so the user can validate their
    api_base / api_key / model_name combination without persisting.
    """
    import time
    from app.llm.client import call_llm
    from app.models.review import LLMModel as _LLMModel

    proto = _LLMModel(
        name=payload.name or "(unsaved)",
        protocol=payload.protocol or LLMProtocol.OPENAI,
        api_base=payload.api_base,
        api_key=payload.api_key,
        model_name=payload.model_name,
        is_active=True,
        priority=1,
    )

    start = time.perf_counter()
    try:
        test_prompt = "请回复「OK,连通测试成功」这 8 个字,不要回复其他任何内容。"
        response = await call_llm(proto, test_prompt, timeout=20)
    except Exception as exc:  # pragma: no cover
        elapsed = int((time.perf_counter() - start) * 1000)
        return LLMTestResult(
            success=False,
            message=f"调用异常: {exc}",
            model_used=proto.model_name,
            latency_ms=elapsed,
        )
    elapsed = int((time.perf_counter() - start) * 1000)

    if response.success:
        snippet = (response.content or "").strip().replace(chr(10), " ")
        if len(snippet) > 120:
            snippet = snippet[:120] + "…"
        if not snippet:
            return LLMTestResult(
                success=False,
                message="API 返回了空内容,请检查模型名或 API 地址是否正确",
                model_used=response.model_used,
                latency_ms=elapsed,
            )
        return LLMTestResult(
            success=True,
            message=f"连通正常,API 已成功返回结果。模型回复: {snippet}",
            model_used=response.model_used,
            latency_ms=elapsed,
        )
    return LLMTestResult(
        success=False,
        message=response.error or "调用失败",
        model_used=response.model_used,
        latency_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Review Rules
# ---------------------------------------------------------------------------
@router.get(
    "/rules",
    response_model=List[ReviewRuleResponse],
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def list_review_rules(
    db: AsyncSession = Depends(get_db),
):
    """List all review rules (SUPER_ADMIN only)."""
    result = await db.execute(
        select(ReviewRule).order_by(ReviewRule.review_type)
    )
    return [ReviewRuleResponse.model_validate(r) for r in result.scalars().all()]


def _validate_model_ids(
    db: AsyncSession,
    llm_model_id: uuid.UUID,
    fallback_model_id: Optional[uuid.UUID],
) -> None:
    """No-op placeholder kept for clarity; validation is done via DB queries."""
    # Validation is performed inline in the create/update endpoints to keep
    # a single round-trip to the database.
    return None


async def _ensure_model_exists(
    db: AsyncSession, model_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(LLMModel).where(LLMModel.id == model_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM model {model_id} not found",
        )


@router.post(
    "/rules",
    response_model=ReviewRuleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def create_review_rule(
    payload: ReviewRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_SUPER_ADMIN),
):
    """Create a review rule (SUPER_ADMIN only).

    Each review type may only have a single active rule; attempting to
    create a duplicate for an existing review type returns 409.
    """
    # Verify referenced models exist.
    await _ensure_model_exists(db, payload.llm_model_id)
    if payload.fallback_model_id is not None:
        await _ensure_model_exists(db, payload.fallback_model_id)

    # Enforce uniqueness of review_type.
    existing = await db.execute(
        select(ReviewRule).where(ReviewRule.review_type == payload.review_type)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A rule for review type '{payload.review_type.value}' already exists",
        )

    rule = ReviewRule(
        review_type=payload.review_type,
        llm_model_id=payload.llm_model_id,
        fallback_model_id=payload.fallback_model_id,
        prompt_template=payload.prompt_template,
        pass_threshold=payload.pass_threshold,
        dimension_thresholds=payload.dimension_thresholds,
        is_active=payload.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    await db.refresh(rule, attribute_names=["llm_model", "fallback_model"])

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="create_review_rule",
        resource_type="review_rule",
        resource_id=str(rule.id),
        details={"review_type": rule.review_type.value},
    )

    return ReviewRuleResponse.model_validate(rule)


@router.put(
    "/rules/{rule_id}",
    response_model=ReviewRuleResponse,
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def update_review_rule(
    rule_id: uuid.UUID,
    payload: ReviewRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_SUPER_ADMIN),
):
    """Update a review rule (SUPER_ADMIN only)."""
    result = await db.execute(
        select(ReviewRule)
        .options(
            selectinload(ReviewRule.llm_model),
            selectinload(ReviewRule.fallback_model),
        )
        .where(ReviewRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review rule not found",
        )

    updates = payload.model_dump(exclude_unset=True)

    # Validate referenced models if they are being changed.
    if "llm_model_id" in updates and updates["llm_model_id"] is not None:
        await _ensure_model_exists(db, updates["llm_model_id"])
    if "fallback_model_id" in updates and updates["fallback_model_id"] is not None:
        await _ensure_model_exists(db, updates["fallback_model_id"])

    for field_name, value in updates.items():
        setattr(rule, field_name, value)

    await db.commit()
    await db.refresh(rule)
    await db.refresh(rule, attribute_names=["llm_model", "fallback_model"])

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="update_review_rule",
        resource_type="review_rule",
        resource_id=str(rule.id),
        details=updates,
    )

    return ReviewRuleResponse.model_validate(rule)


@router.delete(
    "/rules/{rule_id}",
    response_model=dict,
    dependencies=[Depends(_SUPER_ADMIN)],
)
async def delete_review_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_SUPER_ADMIN),
):
    """Physically delete a review rule (SUPER_ADMIN only).

    Historical LLMReview records are not affected because they store
    ``review_type`` as a string, not a foreign key to the rule.
    """
    result = await db.execute(
        select(ReviewRule)
        .options(
            selectinload(ReviewRule.llm_model),
            selectinload(ReviewRule.fallback_model),
        )
        .where(ReviewRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review rule not found",
        )

    snapshot = {
        "id": str(rule.id),
        "review_type": rule.review_type.value if rule.review_type else None,
        "llm_model_id": str(rule.llm_model_id) if rule.llm_model_id else None,
    }

    await db.delete(rule)
    await db.commit()

    await create_audit_log(
        db=db,
        user_id=current_user.id,
        action="delete_review_rule",
        resource_type="review_rule",
        resource_id=str(rule_id),
        details=snapshot,
    )

    return {"deleted": True, "id": str(rule_id)}
