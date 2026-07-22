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

import asyncio
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
def _build_openai_url(api_base: str) -> str:
    """Build the OpenAI-compatible chat completions URL.

    Supports all common api_base formats:
        https://api.openai.com                          -> .../v1/chat/completions
        https://api.openai.com/                         -> .../v1/chat/completions
        https://api.openai.com/v1                       -> .../v1/chat/completions
        https://api.openai.com/v1/                      -> .../v1/chat/completions
        https://api.openai.com/v1/chat/completions      -> (as-is)
        https://api.openai.com/chat/completions         -> (as-is, non-standard but accepted)
    """
    url = (api_base or "").rstrip("/")
    if not url:
        raise ValueError("api_base 不能为空")
    # 已含完整路径(最常见情况),直接使用
    if url.endswith("/chat/completions"):
        return url
    # 已含 /v1 前缀,只需补 /chat/completions
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    # 其他情况:统一补 /v1/chat/completions
    return f"{url}/v1/chat/completions"


def _build_anthropic_url(api_base: str) -> str:
    """Build the Anthropic-native messages URL.

    Supports:
        https://api.anthropic.com                  -> .../v1/messages
        https://api.anthropic.com/                 -> .../v1/messages
        https://api.anthropic.com/v1               -> .../v1/messages
        https://api.anthropic.com/v1/               -> .../v1/messages
        https://api.anthropic.com/v1/messages       -> (as-is)
    """
    url = (api_base or "").rstrip("/")
    if not url:
        raise ValueError("api_base 不能为空")
    if url.endswith("/v1/messages"):
        return url
    if url.endswith("/v1"):
        return f"{url}/messages"
    return f"{url}/v1/messages"


async def _call_openai(
    model: LLMModel,
    prompt: str,
    timeout: int,
) -> LLMResponse:
    """Call an OpenAI-compatible ``/chat/completions`` endpoint."""
    try:
        url = _build_openai_url(model.api_base)
    except ValueError as exc:
        return LLMResponse.failure(str(exc), model_used=model.model_name)

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
        # P2-2: max_tokens 改为从 settings 读取,便于环境变量覆盖
        # Reasoning models (minimax-M3, DeepSeek-R1) emit a <think> block
        # before the final JSON; 4096 is too small and the JSON gets
        # truncated. 8192 leaves room for both reasoning and the payload.
        "max_tokens": settings.LLM_MAX_TOKENS_OPENAI,
    }

    try:
        # P2-1: 区分连接超时与读取超时,连接 10 秒,读取使用传入 timeout
        timeout_config = httpx.Timeout(connect=10, read=timeout or 300, write=10, pool=10)
        async with httpx.AsyncClient(timeout=timeout_config) as client:
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
        # 加入 URL 诊断信息,帮助用户排查 API 地址问题
        hint = ""
        if response.status_code == 404:
            hint = " | URL 诊断:API 地址可能不正确(404)。请确认 api_base 是否指向 OpenAI 兼容接口根路径(系统会自动补 /v1/chat/completions)。"
        elif response.status_code == 401:
            hint = " | URL 诊断:认证失败(401)。请检查 api_key 是否正确。"
        elif response.status_code == 403:
            hint = " | URL 诊断:权限被拒(403)。请检查 api_key 是否有访问该模型的权限。"
        return LLMResponse.failure(
            f"HTTP {response.status_code}: {body}{hint}",
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
            "Response missing choices[0].message.content (URL 可能不正确或返回的不是 OpenAI 协议格式)",
            model_used=model.model_name,
        )

    if not content or not content.strip():
        return LLMResponse.failure(
            "模型返回空内容,请检查模型名是否正确或上下文是否超限",
            model_used=model.model_name,
        )

    return LLMResponse.ok(content=content, model_used=model.model_name)


async def _call_openai_stream(
    model: LLMModel,
    prompt: str,
    timeout: int,
    progress_callback=None,
) -> LLMResponse:
    """流式调用 OpenAI 兼容 ``/chat/completions`` 接口。

    通过 ``progress_callback("chunk", delta)`` 把每个流式片段推送给前端,
    实现"LLM 流式返回文字实时显示"的效果。
    如果流式过程中出现网络异常但已收到部分内容,返回部分内容(容错);
    如果完全没有收到内容,返回失败以便上层回退到非流式重试。
    """
    try:
        url = _build_openai_url(model.api_base)
    except ValueError as exc:
        return LLMResponse.failure(str(exc), model_used=model.model_name)

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
        "max_tokens": settings.LLM_MAX_TOKENS_OPENAI,
        "stream": True,
    }

    content_parts: list[str] = []

    try:
        timeout_config = httpx.Timeout(connect=10, read=timeout or 300, write=10, pool=10)
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    body_text = body.decode("utf-8", errors="replace")[:500]
                    return LLMResponse.failure(
                        f"HTTP {response.status_code}: {body_text}",
                        model_used=model.model_name,
                    )
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    chunk_data = line[6:]
                    if chunk_data == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(chunk_data)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = chunk_json["choices"][0]["delta"].get("content", "")
                    except (KeyError, IndexError, TypeError):
                        delta = ""
                    if delta:
                        content_parts.append(delta)
                        if progress_callback:
                            try:
                                await progress_callback("chunk", delta)
                            except Exception:  # noqa: BLE001
                                pass
    except httpx.TimeoutException:
        # 流式超时:如果有部分内容,返回部分内容;否则返回失败
        if content_parts:
            content = "".join(content_parts)
            if content.strip():
                logger.warning("LLM stream timed out but got partial content (%s chars)", len(content))
                return LLMResponse.ok(content=content, model_used=model.model_name)
        return LLMResponse.failure(
            f"Stream timed out after {timeout}s", model_used=model.model_name
        )
    except (httpx.HTTPError, ConnectionError) as exc:
        if content_parts:
            content = "".join(content_parts)
            if content.strip():
                logger.warning("LLM stream error but got partial content: %s", exc)
                return LLMResponse.ok(content=content, model_used=model.model_name)
        return LLMResponse.failure(f"HTTP error: {exc}", model_used=model.model_name)

    content = "".join(content_parts)
    if not content or not content.strip():
        return LLMResponse.failure(
            "模型返回空内容,请检查模型名是否正确或上下文是否超限",
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
    try:
        url = _build_anthropic_url(model.api_base)
    except ValueError as exc:
        return LLMResponse.failure(str(exc), model_used=model.model_name)

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
        # P2-2: max_tokens 改为从 settings 读取,便于环境变量覆盖
        "max_tokens": settings.LLM_MAX_TOKENS_ANTHROPIC,
    }

    try:
        # P2-1: 区分连接超时与读取超时,连接 10 秒,读取使用传入 timeout
        timeout_config = httpx.Timeout(connect=10, read=timeout or 300, write=10, pool=10)
        async with httpx.AsyncClient(timeout=timeout_config) as client:
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
        hint = ""
        if response.status_code == 404:
            hint = " | URL 诊断:API 地址可能不正确(404)。请确认 api_base 是否指向 Anthropic 兼容接口根路径(系统会自动补 /v1/messages)。"
        elif response.status_code == 401:
            hint = " | URL 诊断:认证失败(401)。请检查 api_key 是否正确。"
        elif response.status_code == 403:
            hint = " | URL 诊断:权限被拒(403)。请检查 api_key 是否有访问该模型的权限。"
        return LLMResponse.failure(
            f"HTTP {response.status_code}: {body}{hint}",
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
            "Response missing content[].text (URL 可能不正确或返回的不是 Anthropic 协议格式)",
            model_used=model.model_name,
        )

    if not content or not content.strip():
        return LLMResponse.failure(
            "模型返回空内容,请检查模型名是否正确或上下文是否超限",
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
    progress_callback=None,
) -> LLMResponse:
    """调用 LLM,支持重试。

    对瞬时网络错误(超时/连接错误)和可重试的 HTTP 错误进行指数退避重试,
    重试次数由 ``settings.LLM_MAX_RETRIES`` 控制。
    认证错误(401/403)或参数错误(400)不会重试,直接返回。

    Args:
        model: :class:`LLMModel` 配置(protocol / api_base / api_key / model_name)。
        prompt: 发送给模型的用户提示词。
        timeout: 请求超时秒数,默认使用 ``settings.LLM_TIMEOUT``。

    Returns:
        :class:`LLMResponse`:成功时 ``content`` 为模型输出文本,
        ``model_used`` 为模型名;失败时 ``success`` 为 ``False``,
        ``error`` 描述失败原因。
    """
    if timeout is None:
        timeout = settings.LLM_TIMEOUT

    # 重试次数由配置控制,允许 0 次重试(只调用一次)
    max_retries = settings.LLM_MAX_RETRIES
    last_error: Optional[str] = None
    last_response: Optional[LLMResponse] = None

    for attempt in range(max_retries + 1):
        try:
            if model.protocol == LLMProtocol.ANTHROPIC:
                # Anthropic 暂不支持流式 chunk 推送(协议差异较大)
                response = await _call_anthropic(model, prompt, timeout)
            elif progress_callback:
                # OpenAI 兼容协议 + 有 callback:优先流式,失败回退非流式
                response = await _call_openai_stream(
                    model, prompt, timeout, progress_callback
                )
                if not response.success:
                    logger.info(
                        "LLM 流式调用失败(%s),回退非流式",
                        response.error,
                    )
                    response = await _call_openai(model, prompt, timeout)
            else:
                # 默认: OpenAI 兼容协议(非流式)
                response = await _call_openai(model, prompt, timeout)

            # 成功则直接返回
            if response.success:
                return response

            # 认证错误(401/403)或参数错误(400)不重试,直接返回
            if response.error and (
                "HTTP 401" in response.error
                or "HTTP 403" in response.error
                or "HTTP 400" in response.error
            ):
                return response

            last_response = response
            last_error = response.error
        except (httpx.TimeoutException, httpx.NetworkError, ConnectionError) as exc:
            # 兜底:理论上 _call_* 已捕获这些异常并转为 LLMResponse.failure,
            # 此处防御性处理避免重试循环因未捕获异常而中断。
            last_error = str(exc)
            last_response = None

        # 还有重试次数则等待后重试(指数退避:1, 2, 4, 8, 10 秒)
        if attempt < max_retries:
            wait = min(2 ** attempt, 10)
            logger.info(
                "LLM 调用失败,第 %s 次重试(等待 %ss): %s",
                attempt + 1,
                wait,
                last_error,
            )
            await asyncio.sleep(wait)

    # 所有重试都失败:优先返回最后一次响应,否则构造失败响应
    if last_response is not None:
        return last_response
    return LLMResponse.failure(
        f"LLM 调用失败(重试 {max_retries} 次后仍失败): {last_error}",
        model_used=model.model_name,
    )


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------
async def call_llm_with_fallback(
    primary_model: LLMModel,
    fallback_model: Optional[LLMModel],
    prompt: str,
    progress_callback=None,
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
    primary = await call_llm(primary_model, prompt, progress_callback=progress_callback)
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
    # 切换备用模型:推送 step 事件告知前端,fallback 调用不传 callback 避免 chunk 混乱
    if progress_callback:
        try:
            await progress_callback("step", f"主模型失败,切换备用模型({fallback_model.model_name})...")
        except Exception:  # noqa: BLE001
            pass
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

# HTML-style reasoning tags emitted by some providers / wrappers
# (e.g. MiniMax-M3 via OpenAI-compat, vLLM, certain Zhipu GLM deployments):
#    <think>...chain of thought...</think>
# These should also be stripped before parsing JSON. If the closing tag is
# missing (output was truncated mid-thought), drop everything from <think>
# to the end of the string.
_HTML_THINK_BLOCK_RE = re.compile(
    r"<think>.*?(?:</think>|$)",
    re.DOTALL | re.IGNORECASE,
)


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

    # Layout G: MiniMax-M3 detailed review wraps everything under a Chinese
    # top-level key like "评审报告" or "代码评审报告". Unwrap it.
    chinese_wrappers = ("评审报告", "代码评审报告", "测试评审报告", "测试报告评审",
                          "专家评审报告", "评审结果", "review",
                          # Layout H: MiniMax-M3 expert report wraps everything
                          # under "评审结论" / "评审元信息" but those are NOT
                          # wrappers to unwrap - they carry the verdict+scores.
                          # We do NOT add them here; they are handled explicitly below.
                          )
    for wrapper_key in chinese_wrappers:
        wrapper = parsed.get(wrapper_key)
        if isinstance(wrapper, dict):
            for k, v in wrapper.items():
                if k not in parsed:
                    parsed[k] = v
            break

    # Generic single-key unwrap: if there's exactly one top-level key whose
    # value is a dict, and that dict contains known review fields, unwrap it.
    if len(parsed) == 1:
        only_val = next(iter(parsed.values()))
        if isinstance(only_val, dict):
            known_keys = {"total_score", "overall_score", "overall_rating",
                          "overall_assessment", "dimension_scores",
                          "score_breakdown", "conclusion", "结论", "总结",
                          "issues", "findings", "评审人员备注"}
            if known_keys & set(only_val.keys()):
                parsed = only_val

    # --- total_score -------------------------------------------------------
    total_score = None
    score_max = 100.0

    # Try simple top-level fields first.
    for key in ("total_score", "score", "overall_score", "overall_rating"):
        val = parsed.get(key)
        if isinstance(val, (int, float)):
            total_score = float(val)
            break

    # If overall_score is a dict (Layout B / Layout J), dig into it.
    overall = parsed.get("overall_score") or parsed.get("overall_rating")
    if total_score is None and isinstance(overall, dict):
        for key in ("composite", "score", "total", "composite_score",
                    "overall_score", "weighted_total", "total_score",
                    "weighted_average", "average"):
            val = overall.get(key)
            if isinstance(val, (int, float)):
                total_score = float(val)
                break
        if isinstance(overall.get("max"), (int, float)):
            score_max = float(overall["max"])

    # Layout D: overall_assessment wrapper (emitted by minimax-M3).
    # {"overall_assessment": {"score": 4.5, "max_score": 10, "summary": "..."}}
    overall_assessment = parsed.get("overall_assessment")
    if total_score is None and isinstance(overall_assessment, dict):
        for key in ("score", "total", "composite", "overall_score"):
            val = overall_assessment.get(key)
            if isinstance(val, (int, float)):
                total_score = float(val)
                break
        for key in ("max_score", "max", "score_max"):
            val = overall_assessment.get(key)
            if isinstance(val, (int, float)):
                score_max = float(val)
                break
        # Lift summary into conclusion if conclusion is empty (handled later).
        if isinstance(overall_assessment.get("summary"), str) and "summary" not in parsed:
            parsed["summary"] = overall_assessment["summary"]
        # Lift risk_level into risk_points if not present.
        if isinstance(overall_assessment.get("risk_level"), str) and "risk_points" not in parsed:
            parsed["risk_points"] = f"risk_level: {overall_assessment['risk_level']}"

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

    # Layout J: if no dimension_scores field, but overall_score is a dict
    # containing per-dimension numeric scores (e.g. professionalism, completeness),
    # harvest them as dimension_scores.
    if not raw_dims and isinstance(overall, dict):
        composite_keys = ("composite", "score", "total", "composite_score",
                           "overall_score", "weighted_total", "total_score",
                           "weighted_average", "average", "max")
        for dk, dv in overall.items():
            if dk in composite_keys:
                continue
            if isinstance(dv, (int, float)) and dv <= 100:
                raw_dims[dk] = dv
            elif isinstance(dv, dict):
                # Per-dimension dict with score/rating inside.
                for sk in ("score", "rating", "得分", "评分"):
                    sv = dv.get(sk)
                    if isinstance(sv, (int, float)):
                        raw_dims[dk] = sv
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

    # --- Layout H: MiniMax-M3 expert report review (all-Chinese keys) -----
    # Structure: 评审结论.{综合评级, 综合评分.{各维度分数, 加权总分}, 一句话结论}
    #             维度评审详情.<dim>.评分
    #             对原报告的改进建议 [{类别, 优先级, 建议}]
    #             原报告Top 5待改进项 [...]
    # Note: total_score may be 0.0 (default fallback) when no English score
    # fields exist. Trigger on falsy (None or 0.0) to catch Layout H.
    if not total_score:
        verdict = parsed.get("评审结论")
        if isinstance(verdict, dict):
            score_obj = verdict.get("综合评分")
            if isinstance(score_obj, dict):
                # Extract 加权总分 (weighted total score).
                weighted = score_obj.get("加权总分")
                if isinstance(weighted, (int, float)):
                    total_score = float(weighted)
                # Extract per-dimension scores (专业性/完整性/合理性/可操作性).
                for dim_name, dim_val in score_obj.items():
                    if dim_name == "加权总分":
                        continue
                    if isinstance(dim_val, (int, float)) and dim_val <= 100:
                        clean_dims[dim_name] = float(dim_val)
            # Also try 维度评审详情.<dim>.评分 for dimension scores
            # (this is the authoritative per-dimension source in Layout H).
            dim_detail = parsed.get("维度评审详情")
            if isinstance(dim_detail, dict) and dim_detail:
                for dim_key, dim_val in dim_detail.items():
                    if isinstance(dim_val, dict):
                        dv = dim_val.get("评分") or dim_val.get("得分") or dim_val.get("score")
                        if isinstance(dv, (int, float)) and dv <= 100:
                            # Use short name (strip leading "一、"/"二、" etc.)
                            short = re.sub(r"^[一二三四五六七八九十]+[、.\s]*", "", dim_key)
                            clean_dims[short] = float(dv)

    # --- Layout I: MiniMax-M3 with 综合评估 wrapper -------------------------
    # Structure: {"综合评估": {"总分": 73, "总评": "...", "优点": [...], "主要缺陷": [...]}}
    # The total_score from Layout H check above may still be 0.0 if the
    # Chinese verdict key was 综合评估 instead of 评审结论.
    if not total_score:
        overall_zh = parsed.get("综合评估")
        if isinstance(overall_zh, dict):
            for zk in ("总分", "加权总分", "综合分", "综合得分", "总分值"):
                zv = overall_zh.get(zk)
                if isinstance(zv, (int, float)):
                    total_score = float(zv)
                    break
            # Lift 总评 into summary for conclusion fallback.
            zp = overall_zh.get("总评")
            if isinstance(zp, str) and "summary" not in parsed:
                parsed["summary"] = zp

    # --- Layout J: verdict dict (MiniMax-M3 with nested wrapper) -----------
    # Structure: {wrapper: {dimension_scores, verdict: {result, rationale}}}
    # If total_score is still falsy but dimension_scores exist, compute average.
    if not total_score and clean_dims:
        dim_vals = [v for v in clean_dims.values() if isinstance(v, (int, float)) and v > 0]
        if dim_vals:
            total_score = sum(dim_vals) / len(dim_vals)

    # --- conclusion --------------------------------------------------------
    # Support both English "conclusion" and Chinese "结论" keys.
    conclusion = parsed.get("conclusion") or parsed.get("结论") or lifted.get("conclusion", "")
    # Layout E (MiniMax-M3 detailed review): conclusion is a dict like
    # {"release_readiness": "NOT READY"/"READY", "blockers": [...],
    #  "summary": "..."}. Render it as readable text.
    # Layout F: conclusion is a Chinese-keyed dict like
    # {"总体评价": "...", "发布建议": "...", "风险等级": "..."}.
    conclusion_blockers: list[str] = []
    if isinstance(conclusion, dict):
        # Layout E (English keys).
        readiness = conclusion.get("release_readiness") or conclusion.get("status") or ""
        blockers = conclusion.get("blockers") or conclusion.get("blocking_issues") or []
        summary_text = conclusion.get("summary") or conclusion.get("description") or ""
        parts: list[str] = []
        if readiness:
            parts.append(f"release_readiness: {readiness}")
        if isinstance(blockers, list):
            conclusion_blockers = [str(b) for b in blockers if b]
            if conclusion_blockers:
                parts.append("blockers:")
                for b in conclusion_blockers:
                    parts.append(f"  - {b}")
        if summary_text:
            parts.append(f"summary: {summary_text}")
        # Layout F (Chinese keys): extract 总体评价/发布建议/风险等级.
        # Layout I (Chinese keys): extract 报告可用性/建议/总评.
        # Layout J (English keys): extract result/rationale (verdict dict).
        if not parts:
            for ck in ("总体评价", "发布建议", "风险等级", "总结", "评审结论",
                       "报告可用性", "建议", "总评",
                       "result", "rationale", "verdict"):
                cv = conclusion.get(ck)
                if isinstance(cv, str) and cv.strip():
                    parts.append(f"{ck}: {cv.strip()}")
                elif isinstance(cv, list):
                    # Some LLMs put issue list under these keys.
                    if ck in ("发布建议", "建议"):
                        for it in cv:
                            if isinstance(it, str) and it.strip():
                                parts.append(f"  - {it.strip()}")
        # Reviewer notes / 评审人员备注.
        reviewer_notes = conclusion.get("评审人员备注") or conclusion.get("备注") or ""
        if isinstance(reviewer_notes, str) and reviewer_notes.strip() and reviewer_notes.strip() not in "\n".join(parts):
            parts.append(f"评审人员备注: {reviewer_notes.strip()}")
        conclusion = "\n".join(parts) if parts else _to_text(conclusion)

    # Top-level Chinese conclusion keys (when "conclusion" itself is missing
    # but 总体评价 / 发布建议 exist at top level).
    if not conclusion:
        top_conclusion_parts: list[str] = []
        for ck in ("总体评价", "发布建议", "风险等级", "总结", "评审结论"):
            cv = parsed.get(ck)
            if isinstance(cv, str) and cv.strip():
                top_conclusion_parts.append(f"{ck}: {cv.strip()}")
        if top_conclusion_parts:
            conclusion = "\n".join(top_conclusion_parts)

    # Top-level reviewer notes.
    if not conclusion:
        rn = parsed.get("评审人员备注") or parsed.get("备注")
        if isinstance(rn, str) and rn.strip():
            conclusion = f"评审人员备注: {rn.strip()}"
    if not conclusion:
        # Layout B: overall_score.summary holds the prose conclusion.
        if isinstance(overall, dict):
            conclusion = overall.get("summary", "")
    if not conclusion:
        # Layout H: 评审结论.综合评级 + 评审结论.一句话结论.
        verdict = parsed.get("评审结论")
        if isinstance(verdict, dict):
            vh_parts: list[str] = []
            grade = verdict.get("综合评级")
            if isinstance(grade, str) and grade.strip():
                vh_parts.append(f"综合评级: {grade.strip()}")
            one_line = verdict.get("一句话结论")
            if isinstance(one_line, str) and one_line.strip():
                vh_parts.append(f"结论: {one_line.strip()}")
            if vh_parts:
                conclusion = "\n".join(vh_parts)
    if not conclusion:
        # Layout J: top-level verdict dict {result, rationale}.
        top_verdict = parsed.get("verdict")
        if isinstance(top_verdict, dict):
            tv_parts: list[str] = []
            for vk in ("result", "rationale", "verdict", "结论"):
                vv = top_verdict.get(vk)
                if isinstance(vv, str) and vv.strip():
                    tv_parts.append(f"{vk}: {vv.strip()}")
            if tv_parts:
                conclusion = "\n".join(tv_parts)
    if not conclusion:
        # Layout C: review_summary.conclusion (already lifted into parsed).
        conclusion = parsed.get("summary", "")

    # --- suggestions & risk_points ----------------------------------------
    suggestions = parsed.get("suggestions", lifted.get("suggestions", ""))
    risk_points = parsed.get("risk_points", lifted.get("risk_points", ""))

    # Layout E: priority_recommendations (list[str]) -> suggestions.
    if not suggestions:
        recs = parsed.get("priority_recommendations") or parsed.get("recommendations")
        if isinstance(recs, list):
            rec_lines = []
            for r in recs:
                if isinstance(r, str) and r.strip():
                    rec_lines.append(f"- {r.strip()}")
                elif isinstance(r, dict):
                    pri = r.get("priority") or r.get("priority_level") or ""
                    items = r.get("items") or r.get("recommendations") or []
                    if isinstance(items, list):
                        for it in items:
                            if isinstance(it, str) and it.strip():
                                tag = f"[{pri}] " if pri else ""
                                rec_lines.append(f"- {tag}{it.strip()}")
                    elif isinstance(r.get("description"), str):
                        tag = f"[{pri}] " if pri else ""
                        rec_lines.append(f"- {tag}{r['description'].strip()}")
            if rec_lines:
                suggestions = "\n".join(rec_lines)

    # Layout E: positive_findings -> prepend to suggestions.
    positives = parsed.get("positive_findings") or parsed.get("strengths")
    if isinstance(positives, list) and positives:
        pos_lines = []
        for p in positives:
            if isinstance(p, str) and p.strip():
                pos_lines.append(f"+ {p.strip()}")
            elif isinstance(p, dict):
                desc = p.get("description") or p.get("summary") or ""
                if desc:
                    pos_lines.append(f"+ {desc}")
        if pos_lines:
            prefix = "positive findings:\n" + "\n".join(pos_lines) + "\n\n"
            suggestions = prefix + (suggestions if isinstance(suggestions, str) else "")

    # Layout E: cross_cutting_issues (list[dict]) -> risk_points.
    if not risk_points:
        cross = parsed.get("cross_cutting_issues") or parsed.get("cross_cutting")
        if isinstance(cross, list):
            cross_lines = []
            for c in cross:
                if not isinstance(c, dict):
                    continue
                cid = c.get("id") or ""
                sev = c.get("severity") or ""
                cat = c.get("category") or ""
                desc = c.get("description") or c.get("issue") or ""
                tag = f"[{sev}]" if sev else ""
                cid_tag = f"[{cid}]" if cid else ""
                cat_tag = f"[{cat}]" if cat else ""
                prefix_parts = [p for p in [tag, cid_tag, cat_tag] if p]
                prefix_str = " ".join(prefix_parts) + " " if prefix_parts else ""
                if desc:
                    cross_lines.append(f"{prefix_str}{desc}")
            if cross_lines:
                risk_points = "\n".join(cross_lines)

    # Layout E: conclusion.blockers -> prepend to risk_points.
    if conclusion_blockers:
        blockers_text = "blockers (from conclusion):\n" + "\n".join(
            f"  - {b}" for b in conclusion_blockers
        )
        risk_points = (blockers_text + "\n\n" + risk_points) if risk_points else blockers_text

    # Layout E/F: if no total_score was found but we have issue counts,
    # estimate a score based on issue severity.
    if total_score == 0.0:
        # Count issues by severity from various sources.
        all_issues = []
        for src_key in ("issues", "critical_issues", "risks", "blockers",
                          "findings", "defects", "cross_cutting_issues"):
            src = parsed.get(src_key)
            if isinstance(src, list):
                all_issues.extend(src)

        # Layout F: Chinese-keyed top-level dimensions. Each value is a dict
        # containing sub-categories like "重大问题", "亮点", "改进建议".
        # Treat these as dimension metadata and harvest nested issue lists.
        chinese_severity_map = {
            "重大问题": "critical", "严重问题": "critical", "阻塞发布": "critical",
            "高优先级": "high", "高": "high",
            "中优先级": "medium", "中": "medium", "中等": "medium",
            "低优先级": "low", "低": "low",
            "立即改进": "high", "短期改进": "medium", "中长期改进": "low",
            "改进建议": "medium", "建议": "low",
            "问题": "medium", "亮点": None,
        }
        chinese_conclusion_keys = ("结论", "总结", "评审结论", "总体评价", "发布建议", "风险等级")
        chinese_conclusion_parts: list[str] = []

        # Iterate top-level keys to find Chinese dimension dicts.
        for top_key, top_val in list(parsed.items()):
            if not isinstance(top_val, dict):
                continue
            # Skip known English structural keys.
            if top_key in ("overall_assessment", "overall_score", "overall_rating",
                            "review_summary", "review_metadata", "metadata",
                            "conclusion", "summary", "files", "file_level_findings"):
                continue
            # Layout F: extract conclusion sub-fields from "结论" dict.
            if top_key in chinese_conclusion_keys:
                for ck in ("总体评价", "发布建议", "风险等级", "summary", "description"):
                    cv = top_val.get(ck)
                    if isinstance(cv, str) and cv.strip():
                        chinese_conclusion_parts.append(f"{ck}: {cv.strip()}")
                continue
            # Otherwise, treat as a dimension with Chinese-named sub-categories.
            dim_score_val = None
            for sk in ("score", "rating", "得分", "评分"):
                sv = top_val.get(sk)
                if isinstance(sv, (int, float)):
                    dim_score_val = float(sv)
                    break
            if dim_score_val is not None:
                # Scale 0-10 up to 0-100.
                if dim_score_val <= 10:
                    dim_score_val = dim_score_val * 10.0
                clean_dims[top_key] = dim_score_val
            # Collect nested issue lists.
            for sub_key, sub_val in top_val.items():
                if not isinstance(sub_val, list):
                    continue
                sev = chinese_severity_map.get(sub_key)
                for it in sub_val:
                    if isinstance(it, str) and it.strip():
                        all_issues.append({
                            "severity": sev or "medium",
                            "description": it.strip(),
                            "category": top_key,
                        })
                    elif isinstance(it, dict):
                        enriched = dict(it)
                        if "severity" not in enriched and sev:
                            enriched["severity"] = sev
                        if "category" not in enriched and top_key:
                            enriched["category"] = top_key
                        all_issues.append(enriched)

        # If conclusion was empty, use Layout F chinese_conclusion_parts.
        if not conclusion and chinese_conclusion_parts:
            conclusion = "\n".join(chinese_conclusion_parts)

        # Also count from dimension_scores metadata.
        for meta in dim_meta.values():
            if isinstance(meta, dict):
                for k in ("issues", "critical_issues", "risks", "blockers"):
                    v = meta.get(k)
                    if isinstance(v, list):
                        all_issues.extend(v)
        if all_issues:
            critical_count = 0
            high_count = 0
            medium_count = 0
            low_count = 0
            for issue in all_issues:
                if isinstance(issue, dict):
                    sev_raw = (issue.get("severity") or issue.get("level") or "").lower()
                    # Map both English and Chinese severities.
                    sev_aliases = {
                        "critical": "critical", "blocker": "critical", "fatal": "critical",
                        "严重": "critical", "致命": "critical", "阻塞": "critical",
                        "high": "high", "高": "high", "高优先级": "high",
                        "medium": "medium", "中": "medium", "中等": "medium",
                        "low": "low", "低": "low", "低优先级": "low",
                    }
                    sev = sev_aliases.get(sev_raw, sev_raw)
                    if sev in ("critical", "blocker", "fatal"):
                        critical_count += 1
                    elif sev == "high":
                        high_count += 1
                    elif sev == "medium":
                        medium_count += 1
                    elif sev == "low":
                        low_count += 1
            # Start from 100 and deduct based on severity.
            # Heuristic: critical=20pts, high=10pts, medium=5pts, low=2pts.
            # Floor at 0. This is a fallback when LLM did not provide a score.
            estimated = 100 - (critical_count * 20 + high_count * 10
                                + medium_count * 5 + low_count * 2)
            if estimated < 0:
                estimated = 0
            # Only use estimated if we actually found issues (avoid false 100).
            if critical_count + high_count + medium_count + low_count > 0:
                total_score = float(estimated)
                # Note: dimension_scores stay empty since LLM didn't provide per-dim scores.

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

    # Layout H/I/J: 对原报告的改进建议 / 对报告的改进建议 / improvement_recommendations.
    if not suggestions:
        layout_h_recs = (parsed.get("对原报告的改进建议")
                         or parsed.get("对报告的改进建议")
                         or parsed.get("改进建议")
                         or parsed.get("improvement_recommendations"))
        rec_lines = []
        if isinstance(layout_h_recs, list):
            # Layout H: list of dicts [{类别, 优先级, 建议}].
            # Layout J: list of dicts [{priority, item, suggestion}].
            for r in layout_h_recs:
                if isinstance(r, dict):
                    cat = r.get("类别") or r.get("category") or ""
                    pri = r.get("优先级") or r.get("priority") or ""
                    # Description: try 建议 first (Chinese), then item+suggestion (English).
                    desc = (r.get("建议") or r.get("description")
                           or r.get("suggestion") or "")
                    item_text = r.get("item") or ""
                    if not desc and item_text:
                        desc = item_text
                        # If suggestion is separate, append it.
                        sug = r.get("suggestion") or ""
                        if sug and sug != desc:
                            desc = f"{desc} → {sug}"
                    if desc:
                        tag_parts = []
                        if cat:
                            tag_parts.append(cat)
                        if pri:
                            tag_parts.append(pri)
                        tag = f"[{','.join(tag_parts)}] " if tag_parts else ""
                        rec_lines.append(f"- {tag}{desc.strip()}")
                elif isinstance(r, str) and r.strip():
                    rec_lines.append(f"- {r.strip()}")
        elif isinstance(layout_h_recs, dict):
            # Layout I/J: dict of category -> list (strings or dicts).
            for cat, items in layout_h_recs.items():
                if isinstance(items, list):
                    for it in items:
                        if isinstance(it, str) and it.strip():
                            rec_lines.append(f"- [{cat}] {it.strip()}")
                        elif isinstance(it, dict):
                            # Dict with priority/item/suggestion OR 类别/建议.
                            pri = it.get("优先级") or it.get("priority") or ""
                            item_text = it.get("item") or it.get("项目") or ""
                            desc = (it.get("建议") or it.get("description")
                                   or it.get("suggestion") or "")
                            if not desc and item_text:
                                desc = item_text
                                sug = it.get("suggestion") or ""
                                if sug and sug != desc:
                                    desc = f"{desc} → {sug}"
                            if desc:
                                tag = f"[{cat},{pri}] " if pri else f"[{cat}] "
                                rec_lines.append(f"- {tag}{desc.strip()}")
        if rec_lines:
            suggestions = "\n".join(rec_lines)

    # Layout H/I: 原报告Top 5待改进项 + 维度评审详情.<dim>.不足 lists.
    # Also captures Layout I's 综合评估.主要缺陷.
    if not risk_points:
        rh_risks: list[str] = []
        # Top-level list of improvement items.
        top_improvements = parsed.get("原报告Top 5待改进项") or parsed.get("待改进项")
        if isinstance(top_improvements, list):
            for it in top_improvements:
                if isinstance(it, str) and it.strip():
                    rh_risks.append(it.strip())
        # Layout I: 综合评估.主要缺陷 list.
        overall_zh = parsed.get("综合评估")
        if isinstance(overall_zh, dict):
            main_defects = overall_zh.get("主要缺陷") or overall_zh.get("缺陷") or []
            if isinstance(main_defects, list):
                for d in main_defects:
                    if isinstance(d, str) and d.strip():
                        rh_risks.append(d.strip())
                    elif isinstance(d, dict):
                        desc = d.get("description") or d.get("summary") or ""
                        if desc:
                            rh_risks.append(desc)
        # Per-dimension 不足 (shortcomings) lists.
        dim_detail = parsed.get("维度评审详情")
        if isinstance(dim_detail, dict):
            for dim_key, dim_val in dim_detail.items():
                if isinstance(dim_val, dict):
                    shortcomings = dim_val.get("不足") or dim_val.get("issues") or []
                    if isinstance(shortcomings, list):
                        for sc in shortcomings:
                            if isinstance(sc, str) and sc.strip():
                                rh_risks.append(f"[{dim_key}] {sc.strip()}")
                            elif isinstance(sc, dict):
                                desc = sc.get("description") or sc.get("summary") or ""
                                if desc:
                                    rh_risks.append(f"[{dim_key}] {desc}")
        if rh_risks:
            risk_points = "\n".join(rh_risks)

    # Layout J: key_findings dict (logic_issues / missing_elements / compliance_gaps).
    if not risk_points:
        kf = parsed.get("key_findings")
        if isinstance(kf, dict):
            kf_risks: list[str] = []
            for sub_key in ("logic_issues", "missing_elements", "compliance_gaps",
                            "critical_issues", "risks", "blockers"):
                items = kf.get(sub_key)
                if isinstance(items, list):
                    for it in items:
                        if isinstance(it, str) and it.strip():
                            kf_risks.append(f"[{sub_key}] {it.strip()}")
                        elif isinstance(it, dict):
                            desc = (it.get("description") or it.get("summary")
                                   or it.get("item") or "")
                            if desc:
                                kf_risks.append(f"[{sub_key}] {desc}")
            if kf_risks:
                risk_points = "\n".join(kf_risks)

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
    text = _HTML_THINK_BLOCK_RE.sub("", text).strip()
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
