"""Review-related Pydantic schemas."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from app.models.review import LLMProtocol, ReviewResult, ReviewType


class LLMModelCreate(BaseModel):
    """Schema for creating an LLM model configuration."""

    name: str
    protocol: LLMProtocol = LLMProtocol.OPENAI
    api_base: str
    api_key: str
    model_name: str
    is_active: bool = True
    priority: int = 0


class LLMModelResponse(BaseModel):
    """Schema for LLM model responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    protocol: LLMProtocol
    api_base: str
    api_key: str
    model_name: str
    is_active: bool
    priority: int
    created_at: datetime


class ReviewRuleCreate(BaseModel):
    """Schema for creating a review rule."""

    review_type: ReviewType
    llm_model_id: uuid.UUID
    fallback_model_id: Optional[uuid.UUID] = None
    prompt_template: str
    pass_threshold: float = 80.0
    dimension_thresholds: Dict[str, Any] = {}
    is_active: bool = True


class ReviewRuleResponse(BaseModel):
    """Schema for review rule responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    review_type: ReviewType
    llm_model_id: uuid.UUID
    fallback_model_id: Optional[uuid.UUID] = None
    prompt_template: str
    pass_threshold: float
    dimension_thresholds: Dict[str, Any]
    is_active: bool


class LLMReviewResponse(BaseModel):
    """Schema for LLM review responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    release_id: uuid.UUID
    review_type: ReviewType
    review_round: int
    result: ReviewResult
    total_score: Optional[float] = None
    dimension_scores: Optional[Dict[str, Any]] = None
    conclusion: Optional[str] = None
    suggestions: Optional[str] = None
    risk_points: Optional[str] = None
    raw_response: Optional[str] = None
    model_used: Optional[str] = None
    triggered_by: uuid.UUID
    triggered_by_name: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
