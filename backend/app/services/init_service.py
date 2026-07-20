"""Initialization service for default data.

Provides idempotent functions to ensure that essential default data
exists in the database. Called at application startup.
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.review import LLMModel, ReviewRule, ReviewType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default prompt templates for each review type
# ---------------------------------------------------------------------------
_DEFAULT_PROMPT_TEMPLATES: Dict[ReviewType, str] = {
    ReviewType.CODE_REVIEW: (
        "你是一名资深的代码评审专家。请对以下代码包进行评审,从完整性、正确性、性能、安全性四个维度打分(0-100)。\n\n"
        "代码包路径: {code_package_path}\n"
        "变更点描述: {change_notes}\n\n"
        "请按以下 JSON 格式输出评审结果:\n"
        "{{\n"
        '  "total_score": 0-100 的总分,\n'
        '  "dimensions": {{\n'
        '    "completeness": {{"score": 0-100, "comment": "..."}},\n'
        '    "correctness": {{"score": 0-100, "comment": "..."}},\n'
        '    "performance": {{"score": 0-100, "comment": "..."}},\n'
        '    "security": {{"score": 0-100, "comment": "..."}}\n'
        "  }},\n"
        '  "conclusion": "通过/不通过及总体结论",\n'
        '  "suggestions": "改进建议",\n'
        '  "risk_points": "风险点"\n'
        "}}"
    ),
    ReviewType.TEST_REPORT_REVIEW: (
        "你是一名资深的测试报告评审专家。请对以下测试报告进行评审,从完整性、正确性、性能、安全性四个维度打分(0-100)。\n\n"
        "测试报告路径: {test_report_path}\n\n"
        "请按以下 JSON 格式输出评审结果:\n"
        "{{\n"
        '  "total_score": 0-100 的总分,\n'
        '  "dimensions": {{\n'
        '    "completeness": {{"score": 0-100, "comment": "..."}},\n'
        '    "correctness": {{"score": 0-100, "comment": "..."}},\n'
        '    "performance": {{"score": 0-100, "comment": "..."}},\n'
        '    "security": {{"score": 0-100, "comment": "..."}}\n'
        "  }},\n"
        '  "conclusion": "通过/不通过及总体结论",\n'
        '  "suggestions": "改进建议",\n'
        '  "risk_points": "风险点"\n'
        "}}"
    ),
    ReviewType.EXPERT_REPORT_REVIEW: (
        "你是一名资深的专家报告评审专家。请对以下评审报告进行评审,从完整性、正确性、性能、安全性四个维度打分(0-100)。\n\n"
        "评审报告路径: {review_report_path}\n\n"
        "请按以下 JSON 格式输出评审结果:\n"
        "{{\n"
        '  "total_score": 0-100 的总分,\n'
        '  "dimensions": {{\n'
        '    "completeness": {{"score": 0-100, "comment": "..."}},\n'
        '    "correctness": {{"score": 0-100, "comment": "..."}},\n'
        '    "performance": {{"score": 0-100, "comment": "..."}},\n'
        '    "security": {{"score": 0-100, "comment": "..."}}\n'
        "  }},\n"
        '  "conclusion": "通过/不通过及总体结论",\n'
        '  "suggestions": "改进建议",\n'
        '  "risk_points": "风险点"\n'
        "}}"
    ),
}


# 默认维度阈值模板(与前端 LlmConfig.vue 中的 DEFAULT_DIMENSION_TEMPLATE 保持一致)
_DEFAULT_DIMENSION_THRESHOLDS: Dict[str, Any] = {
    "completeness": {"threshold": 70, "weight": 0.3, "description": "完整性 - 功能覆盖、文档齐全"},
    "correctness": {"threshold": 70, "weight": 0.4, "description": "正确性 - 逻辑正确、无缺陷"},
    "performance": {"threshold": 70, "weight": 0.2, "description": "性能 - 响应时间、资源占用"},
    "security": {"threshold": 70, "weight": 0.1, "description": "安全性 - 漏洞、权限控制"},
}


async def ensure_default_review_rules() -> None:
    """Ensure that default review rules exist for all review types.

    This function is idempotent: it only creates rules for review types
    that don't have one yet. If no active LLM model exists, it skips
    creation (the admin must create an LLM model first).

    Called at application startup.
    """
    async with async_session_factory() as db:
        # 1. 检查是否已有任何 active LLM model
        result = await db.execute(
            select(LLMModel)
            .where(LLMModel.is_active.is_(True))
            .order_by(LLMModel.priority.desc(), LLMModel.created_at)
        )
        active_models = result.scalars().all()
        if not active_models:
            logger.info(
                "ensure_default_review_rules: 没有启用的 LLM 模型,跳过默认规则创建。"
                "请先在 LLM 配置页创建并启用至少一个模型。"
            )
            return

        primary_model = active_models[0]
        fallback_model = active_models[1] if len(active_models) > 1 else None

        # 2. 为每个 review_type 创建缺失的规则
        created_count = 0
        for review_type in ReviewType:
            existing = await db.execute(
                select(ReviewRule).where(ReviewRule.review_type == review_type)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            rule = ReviewRule(
                review_type=review_type,
                llm_model_id=primary_model.id,
                fallback_model_id=fallback_model.id if fallback_model else None,
                prompt_template=_DEFAULT_PROMPT_TEMPLATES[review_type],
                pass_threshold=60.0,
                dimension_thresholds=_DEFAULT_DIMENSION_THRESHOLDS,
                is_active=True,
            )
            db.add(rule)
            created_count += 1
            logger.info(
                "ensure_default_review_rules: 为 %s 创建默认评审规则,"
                "主模型=%s, fallback=%s",
                review_type.value,
                primary_model.name,
                fallback_model.name if fallback_model else "无",
            )

        if created_count > 0:
            await db.commit()
            logger.info(
                "ensure_default_review_rules: 共创建 %d 条默认评审规则", created_count
            )
        else:
            logger.info("ensure_default_review_rules: 所有评审类型已有规则,无需创建")
