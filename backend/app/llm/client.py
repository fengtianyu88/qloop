"""LLM API client.

A thin async wrapper around two API protocols used by the review engine:

* **OpenAI-compatible** (``/chat/completions``) — used by OpenAI, vLLM,
  TGI, Ollama, 通义千问, DeepSeek, and most self-hosted gateways.
* **Anthropic native** (``/v1/messages``) — used by Claude series models.

The client is intentionally generic: it talks to any service that accepts
one of the two standard request schemas and normalizes the result into a
single :class:`LLMResponse`.

Highlights:
    * :class:`LLMResponse` - normalized result of an LLM call.
    * :func:`call_llm` - call a single model (auto-dispatches by protocol).
    * :func:`call_llm_with_fallback` - call a primary model and fall back
      to a secondary model on failure.
    * :func:`parse_llm_review_result` - robustly extract the JSON review
      payload from a model response.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings
from app.models.review import LLMModel, LLMProtocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response container
# ---------------------------------------------------------------------------
@dataclass
class LLMResponse:
    """Normalized result of an LLM API call."""

    content: Optional[str]
    model_used: Optional[str]
    success: bool
    error: Optional[str] = None

    @classmethod
    def ok(cls, content: str, model_used: str) -> "LLMResponse":
        return cls(content=content, model_used=model_used, success=True)

    @classmethod
    def failure(cls, error: str, model_used: Optional[str] = None) -> "LLMResponse":
        return cls(content=None, model_used=model_used, success=False, error=error)


# ---------------------------------------------------------------------------
# OpenAI-compatible call (/chat/completions)
# ---------------------------------------------------------------------------
async def _call_openai(
    model: LLMModel,
    prompt: str,
    timeout: int,
) -> LLMResponse:
    """Call an OpenAI-compatible ``/chat/completions`` endpoint."""
    url = model.api_base.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {model.api_key}",
    }
    payload = {
        "model": model.model_name,
        "messages": [
            {"role": "system", "content": "你是一位严谨的软件评审专家助手，只输出JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException:
        logger.warning("LLM (openai) call to %s timed out after %ss", url, timeout)
        return LLMResponse.failure(
            f"Request timed out after {timeout}s", model_used=model.model_name
        )
    except httpx.HTTPError as exc:
        logger.warning("LLM (openai) call to %s failed: %s", url, exc)
        return LLMResponse.failure(f"HTTP error: {exc}", model_used=model.model_name)

    if response.status_code >= 400:
        body = response.text[:500]
        logger.warning(
            "LLM (openai) call to %s returned HTTP %s: %s",
            url,
            response.status_code,
            body,
        )
        return LLMResponse.failure(
            f"HTTP {response.status_code}: {body}",
            model_used=model.model_name,
        )

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        return LLMResponse.failure(
            f"Invalid JSON response: {exc}", model_used=model.model_name
        )

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return LLMResponse.failure(
            "Response missing choices[0].message.content",
            model_used=model.model_name,
        )

    return LLMResponse.ok(content=content, model_used=model.model_name)


# ---------------------------------------------------------------------------
# Anthropic native call (/v1/messages)
# ---------------------------------------------------------------------------
async def _call_anthropic(
    model: LLMModel,
    prompt: str,
    timeout: int,
) -> LLMResponse:
    """Call an Anthropic-native ``/v1/messages`` endpoint (Claude).

    The Anthropic API differs from OpenAI in three key ways:
        * URL path is ``/v1/messages`` instead of ``/chat/completions``.
        * Auth header is ``x-api-key`` (+ ``anthropic-version``) instead of
          ``Authorization: Bearer``.
        * Response shape is ``content[0].text`` instead of
          ``choices[0].message.content``; the system prompt is a top-level
          ``system`` field rather than a chat message.
    """
    url = model.api_base.rstrip("/")
    if not url.endswith("/v1/messages"):
        # Allow api_base like "https://api.anthropic.com" or ".../v1"
        if url.endswith("/v1"):
            url = f"{url}/messages"
        else:
            url = f"{url}/v1/messages"

    headers = {
        "Content-Type": "application/json",
        "x-api-key": model.api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model.model_name,
        "system": "你是一位严谨的软件评审专家助手，只输出JSON。",
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException:
        logger.warning("LLM (anthropic) call to %s timed out after %ss", url, timeout)
        return LLMResponse.failure(
            f"Request timed out after {timeout}s", model_used=model.model_name
        )
    except httpx.HTTPError as exc:
        logger.warning("LLM (anthropic) call to %s failed: %s", url, exc)
        return LLMResponse.failure(f"HTTP error: {exc}", model_used=model.model_name)

    if response.status_code >= 400:
        body = response.text[:500]
        logger.warning(
            "LLM (anthropic) call to %s returned HTTP %s: %s",
            url,
            response.status_code,
            body,
        )
        return LLMResponse.failure(
            f"HTTP {response.status_code}: {body}",
            model_used=model.model_name,
        )

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        return LLMResponse.failure(
            f"Invalid JSON response: {exc}", model_used=model.model_name
        )

    # Anthropic response: {"content": [{"type": "text", "text": "..."}], ...}
    try:
        content_blocks = data["content"]
        if not content_blocks:
            raise KeyError("content is empty")
        # Concatenate all text blocks (there may be multiple).
        parts = [
            block.get("text", "")
            for block in content_blocks
            if block.get("type") == "text"
        ]
        content = "".join(parts)
        if not content:
            raise KeyError("no text block found in content")
    except (KeyError, IndexError, TypeError):
        return LLMResponse.failure(
            "Response missing content[].text",
            model_used=model.model_name,
        )

    return LLMResponse.ok(content=content, model_used=model.model_name)


# ---------------------------------------------------------------------------
# Core call (dispatches by protocol)
# ---------------------------------------------------------------------------
async def call_llm(
    model: LLMModel,
    prompt: str,
    timeout: Optional[int] = None,
) -> LLMResponse:
    """Call an LLM endpoint, dispatching by the model's configured protocol.

    Args:
        model: The :class:`LLMModel` configuration (protocol, api_base,
            api_key, model_name).
        prompt: The user prompt to send.
        timeout: Optional request timeout in seconds. Defaults to
            ``settings.LLM_TIMEOUT``.

    Returns:
        An :class:`LLMResponse`. On success ``content`` holds the model's
        message text and ``model_used`` the model name; on failure
        ``success`` is ``False`` and ``error`` describes the problem.
    """
    if timeout is None:
        timeout = settings.LLM_TIMEOUT

    if model.protocol == LLMProtocol.ANTHROPIC:
        return await _call_anthropic(model, prompt, timeout)
    # Default: OpenAI-compatible
    return await _call_openai(model, prompt, timeout)


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------
async def call_llm_with_fallback(
    primary_model: LLMModel,
    fallback_model: Optional[LLMModel],
    prompt: str,
) -> LLMResponse:
    """Call the primary model, falling back to a secondary on failure.

    A "failure" is any non-success :class:`LLMResponse` from the primary
    model. If no fallback model is configured (``None``), the primary
    result is returned as-is.

    Args:
        primary_model: The preferred model to call first.
        fallback_model: The fallback model, or ``None``.
        prompt: The prompt to send.

    Returns:
        The :class:`LLMResponse` from the primary model if it succeeded,
        otherwise from the fallback model (which may also be a failure).
    """
    primary = await call_llm(primary_model, prompt)
    if primary.success:
        return primary

    if fallback_model is None:
        return primary

    logger.info(
        "Primary model %s failed (%s); falling back to %s",
        primary_model.model_name,
        primary.error,
        fallback_model.model_name,
    )
    fallback = await call_llm(fallback_model, prompt)
    if not fallback.success:
        # Annotate the fallback error with the primary error for context.
        fallback.error = (
            f"primary={primary_model.model_name} failed ({primary.error}); "
            f"fallback={fallback_model.model_name} failed ({fallback.error})"
        )
    return fallback


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------
_JSON_CODE_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _default_failed_result(reason: str) -> dict:
    """Return the default dict used when the LLM result cannot be parsed."""
    return {
        "total_score": 0,
        "dimension_scores": {},
        "conclusion": "failed",
        "suggestions": f"无法解析 LLM 评审结果: {reason}",
        "risk_points": "LLM 返回内容无法解析为有效 JSON",
    }


def parse_llm_review_result(content: Optional[str]) -> dict:
    """Extract a JSON review payload from an LLM response.

    The function tolerates:
        * `````json ... `````` fenced code blocks.
        * Bare JSON objects embedded in surrounding prose.
        * Trailing commas (removed before parsing).

    Args:
        content: The raw text returned by the LLM, or ``None``.

    Returns:
        A dict with keys ``total_score``, ``dimension_scores``,
        ``conclusion``, ``suggestions``, ``risk_points``. If parsing
        fails, a default "failed" result is returned.
    """
    if not content or not content.strip():
        return _default_failed_result("LLM 返回内容为空")

    text = content.strip()

    # 1) Try fenced ```json ... ``` blocks first.
    match = _JSON_CODE_BLOCK_RE.search(text)
    candidates = []
    if match:
        candidates.append(match.group(1).strip())

    # 2) Always also consider the whole text as a candidate.
    candidates.append(text)

    # 3) Extract bare {...} substrings as a last resort.
    brace_candidates = re.findall(r"\{.*\}", text, re.DOTALL)
    candidates.extend(brace_candidates)

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        # Strip a leading "json" marker if the fence was malformed.
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].lstrip()
        # Remove trailing commas before closing braces/brackets (common LLM
        # mistake) to be permissive.
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            # Some LLMs mistakenly nest conclusion/suggestions/risk_points
            # inside dimension_scores. Lift them out to the top level so
            # downstream code can find them.
            raw_dims = parsed.get("dimension_scores", {}) or {}
            if not isinstance(raw_dims, dict):
                raw_dims = {}
            extra_keys = ("conclusion", "suggestions", "risk_points")
            lifted = {k: raw_dims[k] for k in extra_keys if k in raw_dims}
            # Build the clean dimension_scores: only numeric entries.
            clean_dims = {
                k: v
                for k, v in raw_dims.items()
                if k not in extra_keys
                and isinstance(v, (int, float, str))
                and str(v).replace(".", "", 1).replace("-", "", 1).isdigit()
            }
            # Top-level fields win over the lifted ones.
            conclusion = parsed.get(
                "conclusion",
                lifted.get("conclusion", ""),
            )
            suggestions = parsed.get(
                "suggestions",
                lifted.get("suggestions", ""),
            )
            risk_points = parsed.get(
                "risk_points",
                lifted.get("risk_points", ""),
            )
            return {
                "total_score": parsed.get("total_score", 0),
                "dimension_scores": clean_dims,
                "conclusion": conclusion if conclusion else "通过",
                "suggestions": suggestions,
                "risk_points": risk_points,
            }

    return _default_failed_result("未找到可解析的 JSON 内容")
