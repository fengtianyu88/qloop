"""Review models: LLMModel, ReviewRule, LLMReview and related enums."""

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReviewType(str, Enum):
    """Type of LLM review."""

    CODE_REVIEW = "code_review"
    TEST_REPORT_REVIEW = "test_report_review"
    EXPERT_REPORT_REVIEW = "expert_report_review"


class ReviewResult(str, Enum):
    """Result of an LLM review."""

    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    ERROR = "error"


class LLMProtocol(str, Enum):
    """API protocol supported by an LLM model.

    * ``OPENAI`` - OpenAI-compatible ``/chat/completions`` endpoint
      (also used by vLLM, TGI, Ollama, 通义千问, DeepSeek, etc.).
    * ``ANTHROPIC`` - Anthropic native ``/v1/messages`` endpoint
      (Claude series).
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMModel(Base):
    """Configuration for an LLM model used in reviews."""

    __tablename__ = "llm_models"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    protocol: Mapped[LLMProtocol] = mapped_column(
        SAEnum(
            LLMProtocol,
            name="llm_protocol",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=LLMProtocol.OPENAI,
        nullable=False,
    )
    api_base: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    review_rules: Mapped[List["ReviewRule"]] = relationship(
        "ReviewRule",
        back_populates="llm_model",
        foreign_keys="ReviewRule.llm_model_id",
    )
    fallback_rules: Mapped[List["ReviewRule"]] = relationship(
        "ReviewRule",
        back_populates="fallback_model",
        foreign_keys="ReviewRule.fallback_model_id",
    )


class ReviewRule(Base):
    """Rule configuration for a review type."""

    __tablename__ = "review_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    review_type: Mapped[ReviewType] = mapped_column(
        SAEnum(ReviewType, name="review_type"),
        unique=True,
        nullable=False,
    )
    llm_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_models.id"), nullable=False
    )
    fallback_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_models.id"), nullable=True
    )
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    pass_threshold: Mapped[float] = mapped_column(
        Float, default=80.0, nullable=False
    )
    dimension_thresholds: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Relationships
    llm_model: Mapped["LLMModel"] = relationship(
        "LLMModel",
        back_populates="review_rules",
        foreign_keys=[llm_model_id],
    )
    fallback_model: Mapped[Optional["LLMModel"]] = relationship(
        "LLMModel",
        back_populates="fallback_rules",
        foreign_keys=[fallback_model_id],
    )


class LLMReview(Base):
    """A single LLM review record for a release."""

    __tablename__ = "llm_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("releases.id"), nullable=False
    )
    review_type: Mapped[ReviewType] = mapped_column(
        SAEnum(ReviewType, name="llm_review_type"),
        nullable=False,
    )
    review_round: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    result: Mapped[ReviewResult] = mapped_column(
        SAEnum(ReviewResult, name="review_result"),
        nullable=False,
        default=ReviewResult.PENDING,
    )
    total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dimension_scores: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )
    conclusion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggestions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_points: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    triggered_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    release: Mapped["Release"] = relationship(
        "Release", back_populates="llm_reviews"
    )
    triggered_by_user: Mapped["User"] = relationship("User")
