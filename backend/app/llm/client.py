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
from typing import Any, Optional

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
        # Reasoning models (minimax-M3, DeepSeek-R1) emit a <think> block
        # before the final JSON; 4096 is too small and the JSON gets
        # truncated. 8192 leaves room for both reasoning and the payload.
        "max_tokens": 8192,
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

# Reasoning models like minimax-M3 / DeepSeek-R1 wrap their chain-of-thought
# in <think>...</think>. If the closing tag is missing (output was truncated
# mid-thought), drop everything from <think> to the end of the string.
_THINK_BLOCK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL)


def _to_text(value: Any) -> str:
    """Coerce a parsed JSON value into a text-safe string.

    LLMs sometimes return structured objects (dict/list) for fields that
    the database schema expects as ``Text`` (e.g. ``conclusion``,
    ``suggestions``, ``risk_points``). This helper ensures any such value
    is converted to a string before being persisted:

    * ``None`` -> ``""``
    * ``str`` -> returned as-is
    * ``dict`` / ``list`` -> pretty-printed via ``json.dumps``
    * other -> ``str(value)``
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _default_failed_result(reason: str) -> dict:
    """Return the default dict used when the LLM result cannot be parsed."""
    return {
        "total_score": 0,
        "dimension_scores": {},
        "conclusion": "failed",
        "suggestions": f"无法解析 LLM 评审结果: {reason}",
        "risk_points": "LLM 返回内容无法解析为有效 JSON",
    }


def _normalize_review_payload(parsed: dict) -> dict:
    """Normalize a parsed LLM review JSON into the flat schema we persist.

    minimax-M3 (and other reasoning models) emit a variety of JSON layouts
    despite the prompt asking for a specific flat schema. This helper
    defensively extracts the score, dimension scores, conclusion,
    suggestions and risk points from any of the known layouts:

    * **Flat** -- ``{"total_score": 85, "dimension_scores": {..}, ..}``
    * **Nested overall_score** -- ``{"overall_score": {"composite": 5.5,
      "max": 10, "summary": ".."}, "dimension_scores": {"dim": {"score": 6}}}``
    * **review_summary wrapper** -- ``{"review_summary": {"overall_score": 52,
      "score_breakdown": {..}, "conclusion": ".."}, "issues": [...]}``

    The output is always the flat schema with ``total_score`` scaled to 0-100.
    """
    # Unwrap a top-level review_summary wrapper (Layout C).
    summary = parsed.get("review_summary")
    if isinstance(summary, dict):
        for k, v in summary.items():
            if k not in parsed:
                parsed[k] = v

    # --- total_score -------------------------------------------------------
    total_score = None
    score_max = 100.0

    # Try simple top-level fields first.
    for key in ("total_score", "score", "overall_score", "overall_rating"):
        val = parsed.get(key)
        if isinstance(val, (int, float)):
            total_score = float(val)
            break

    # If overall_score is a dict (Layout B), dig into it.
    overall = parsed.get("overall_score") or parsed.get("overall_rating")
    if total_score is None and isinstance(overall, dict):
        for key in ("composite", "score", "total"):
            val = overall.get(key)
            if isinstance(val, (int, float)):
                total_score = float(val)
                break
        if isinstance(overall.get("max"), (int, float)):
            score_max = float(overall["max"])

    if total_score is None:
        total_score = 0.0

    # Auto-detect 0-10 scale: if total_score is small (<= 10) and we never
    # saw an explicit `max`, assume the model used a 0-10 scale and scale up.
    # minimax-M3 frequently uses 0-10 despite the prompt asking for 0-100.
    if score_max == 100.0 and total_score <= 10:
        score_max = 10.0

    # Scale 0-10 (or any non-100 max) up to 0-100.
    if score_max and score_max != 100:
        total_score = total_score * (100.0 / score_max)

    # --- dimension_scores --------------------------------------------------
    # Look in several keys; first dict wins.
    raw_dims: dict = {}
    for key in ("dimension_scores", "score_breakdown", "scores", "dimensions"):
        val = parsed.get(key)
        if isinstance(val, dict):
            raw_dims = val
            break

    # Some LLMs nest text fields inside dimension_scores.
    extra_keys = ("conclusion", "suggestions", "risk_points")
    lifted = {k: raw_dims[k] for k in extra_keys if k in raw_dims}

    clean_dims: dict[str, float] = {}
    dim_meta: dict[str, dict] = {}  # stashed for suggestions/risk mining
    for k, v in raw_dims.items():
        if k in extra_keys:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            clean_dims[k] = float(v)
        elif isinstance(v, str):
            try:
                clean_dims[k] = float(v)
            except ValueError:
                pass
        elif isinstance(v, dict):
            dim_meta[k] = v
            sub = v.get("score")
            if sub is None:
                sub = v.get("rating")
            if sub is not None:
                try:
                    clean_dims[k] = float(sub)
                except (TypeError, ValueError):
                    pass

    # Scale per-dimension scores if they appear to be on a sub-100 scale.
    # Auto-detect: if every dimension score is <= 10, assume 0-10 scale.
    if score_max == 100.0 and clean_dims:
        if all(v <= 10 for v in clean_dims.values()):
            score_max = 10.0
    if score_max and score_max != 100:
        for k, v in clean_dims.items():
            if v <= score_max:
                clean_dims[k] = v * (100.0 / score_max)

    # --- conclusion --------------------------------------------------------
    conclusion = parsed.get("conclusion", lifted.get("conclusion", ""))
    if not conclusion:
        # Layout B: overall_score.summary holds the prose conclusion.
        if isinstance(overall, dict):
            conclusion = overall.get("summary", "")
    if not conclusion:
        # Layout C: review_summary.conclusion (already lifted into parsed).
        conclusion = parsed.get("summary", "")

    # --- suggestions & risk_points ----------------------------------------
    suggestions = parsed.get("suggestions", lifted.get("suggestions", ""))
    risk_points = parsed.get("risk_points", lifted.get("risk_points", ""))

    # Collect from nested dimension metadata if top-level fields are empty.
    if not suggestions and dim_meta:
        parts: list[str] = []
        for dim_name, meta in dim_meta.items():
            if not isinstance(meta, dict):
                continue
            for issue_key in ("issues", "suggestions", "improvements"):
                issues = meta.get(issue_key, [])
                if isinstance(issues, list):
                    for issue in issues:
                        _append_issue(parts, dim_name, issue)
        if parts:
            suggestions = "\n".join(parts)

    if not risk_points and dim_meta:
        parts = []
        for dim_name, meta in dim_meta.items():
            if not isinstance(meta, dict):
                continue
            for issue_key in ("critical_issues", "risks", "blockers"):
                issues = meta.get(issue_key, [])
                if isinstance(issues, list):
                    for issue in issues:
                        _append_issue(parts, dim_name, issue)
        if parts:
            risk_points = "\n".join(parts)

    # Layouts C & D: top-level issues / critical_issues / risks arrays.
    # critical_issues -> risk_points; other issues -> suggestions.
    top_issue_sources = ("issues", "critical_issues", "risks", "blockers",
                          "findings", "defects")
    sug_parts: list[str] = []
    risk_parts: list[str] = []
    for src_key in top_issue_sources:
        top_issues = parsed.get(src_key)
        if not isinstance(top_issues, list):
            continue
        for issue in top_issues:
            if isinstance(issue, str) and issue.strip():
                # Bare string issue; route by container name.
                if src_key in ("critical_issues", "risks", "blockers"):
                    risk_parts.append(issue.strip())
                else:
                    sug_parts.append(issue.strip())
                continue
            if not isinstance(issue, dict):
                continue
            # Try many possible field names for the title and detail.
            title = (issue.get("title") or issue.get("summary")
                     or issue.get("issue") or issue.get("name") or "")
            desc = (issue.get("description") or issue.get("detail")
                    or issue.get("impact") or issue.get("effect") or "")
            rec = (issue.get("recommendation") or issue.get("fix")
                   or issue.get("suggestion") or issue.get("remediation") or "")
            sev = (issue.get("severity") or issue.get("level") or "").lower()
            cat = (issue.get("category") or issue.get("type") or "").lower()
            loc = issue.get("file") or issue.get("location") or ""
            line = f"[{sev}] {title}" if sev else title
            if loc:
                line += f" ({loc})"
            if desc:
                line += f": {desc}"
            if rec:
                line += f" => {rec}"
            # Route to risks if the container or severity says so.
            is_risk = (src_key in ("critical_issues", "risks", "blockers")
                       or sev in ("critical", "high", "blocker", "fatal")
                       or cat in ("security", "compliance", "correctness"))
            if is_risk:
                risk_parts.append(line)
            else:
                sug_parts.append(line)
    if not suggestions and sug_parts:
        suggestions = "\n".join(sug_parts)
    if not risk_points and risk_parts:
        risk_points = "\n".join(risk_parts)

    return {
        "total_score": round(total_score),
        "dimension_scores": clean_dims,
        "conclusion": _to_text(conclusion) or "通过",
        "suggestions": _to_text(suggestions),
        "risk_points": _to_text(risk_points),
    }


def _append_issue(parts: list[str], dim_name: str, issue) -> None:
    """Append a single issue (str or dict) to ``parts`` as a formatted line."""
    if isinstance(issue, str) and issue.strip():
        parts.append(f"[{dim_name}] {issue.strip()}")
    elif isinstance(issue, dict):
        title = issue.get("title") or issue.get("summary") or ""
        detail = issue.get("detail") or issue.get("description") or ""
        sev = issue.get("severity") or ""
        if title:
            tag = f"[{sev}] " if sev else ""
            parts.append(f"{tag}[{dim_name}] {title}: {detail}")


def parse_llm_review_result(content: Optional[str]) -> dict:
    """Extract a JSON review payload from an LLM response.

    The function tolerates:
        * ``<think>...</think>`` reasoning blocks (minimax-M3, DeepSeek-R1)
          — stripped before parsing.
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

    # 0) Strip <think>...</think> reasoning blocks emitted by models like
    # minimax-M3 / DeepSeek-R1. If the closing tag is missing (output was
    # truncated mid-thought), drop everything from <think> to the end.
    text = _THINK_BLOCK_RE.sub("", text).strip()
    if not text:
        return _default_failed_result("LLM 返回内容仅含 <think> 推理块")

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
            return _normalize_review_payload(parsed)

    return _default_failed_result("未找到可解析的 JSON 内容")
