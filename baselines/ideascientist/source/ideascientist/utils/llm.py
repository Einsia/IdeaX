"""OpenAI-compatible chat, Responses, and embedding client.

Endpoints, keys, and model names are resolved here from environment variables so
no call site hardcodes them. Any OpenAI-compatible server works: a local vLLM
pool, the OpenAI API, or a gateway.

    IDEASCIENTIST_API_KEY / OPENAI_API_KEY
    IDEASCIENTIST_BASE_URL / OPENAI_BASE_URL   default http://localhost:8000/v1
    IDEASCIENTIST_MODEL                        default Qwen3.6-27B
    IDEASCIENTIST_WIRE_API                     default chat_completions
    IDEASCIENTIST_HTTP_USER_AGENT              default urllib (Codex UA for Responses)
    IDEASCIENTIST_REASONING_EFFORT             Responses reasoning effort (optional)
    IDEASCIENTIST_USE_CODEX_AUTH                opt-in only; default disabled
    IDEASCIENTIST_CODEX_AUTH_FILE               explicit auth-file opt-in
    EMBEDDING_BASE_URL                         default http://localhost:8100/v1
    EMBEDDING_MODEL / EMBEDDING_DIM            default Qwen3-Embedding-0.6B / 1024
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "Qwen3.6-27B"
DEFAULT_WIRE_API = "chat_completions"
DEFAULT_CODEX_USER_AGENT = "codex_cli_rs/0.114.0"

DEFAULT_EMBEDDING_BASE_URL = "http://localhost:8100/v1"
DEFAULT_EMBEDDING_MODEL = "Qwen3-Embedding-0.6B"
DEFAULT_EMBEDDING_DIM = 1024

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 520, 522, 524}


class _RePostRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow 307/308 without urllib's default downgrade of POST to GET."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return urllib.request.Request(
            newurl,
            data=req.data,
            headers=dict(req.header_items()),
            method=req.get_method(),
        )


def build_opener(proxy: str = "") -> urllib.request.OpenerDirector:
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
            _RePostRedirectHandler,
        )
    return urllib.request.build_opener(_RePostRedirectHandler)


class LLMTimeoutError(TimeoutError):
    """A request exceeded its hard total wall-clock deadline."""


def _open_with_deadline(
    opener: urllib.request.OpenerDirector,
    req: urllib.request.Request,
    *,
    sock_timeout: float,
    deadline: float,
) -> bytes:
    """``opener.open() + read()`` bounded by a total wall-clock ``deadline``.

    urllib's ``timeout`` is per-socket-operation, so an endpoint that accepts the
    connection and then trickles bytes never trips it. Under the reward-phase
    concurrency of GRPO training that stalls a whole reward thread, so the
    blocking read runs in a daemon thread we abandon at the deadline.
    """
    box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            with opener.open(req, timeout=sock_timeout) as resp:
                box["body"] = resp.read()
        except BaseException as exc:  # noqa: BLE001 - relayed to the caller thread
            box["exc"] = exc

    t = threading.Thread(target=_worker, name="llm-http", daemon=True)
    t.start()
    t.join(deadline)
    if t.is_alive():
        raise LLMTimeoutError(f"request exceeded hard deadline of {deadline:.0f}s")
    if "exc" in box:
        raise box["exc"]
    return box["body"]


def uses_completion_tokens(model: str) -> bool:
    """True for families that require ``max_completion_tokens``."""
    return bool(re.search(r"(?:^|-)(gpt-?5|o[1-9])", (model or "").lower()))


_CONTEXT_WINDOWS: tuple[tuple[str, int], ...] = (
    ("claude", 200_000),
    ("gpt-5", 400_000),
    ("gpt-oss", 128_000),
    ("gptoss", 128_000),
    ("gemma", 128_000),
    ("qwen", 256_000),
    ("llama-4", 1_000_000),
    ("llama", 128_000),
)
DEFAULT_CONTEXT_WINDOW = 128_000


def context_window_for(model: str) -> int:
    """Context window in tokens, for sizing the per-call output budget."""
    override = os.environ.get("CONTEXT_WINDOW", "").strip()
    if override.isdigit():
        return int(override)
    m = (model or "").lower()
    for needle, window in _CONTEXT_WINDOWS:
        if needle in m:
            return window
    return DEFAULT_CONTEXT_WINDOW


def _env_key(*names: str) -> str:
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return ""


def normalize_wire_api(value: Optional[str] = None) -> str:
    """Return the canonical wire API name, rejecting ambiguous values."""
    wire = (value or os.environ.get("IDEASCIENTIST_WIRE_API") or DEFAULT_WIRE_API)
    wire = wire.strip().lower().replace("-", "_")
    aliases = {
        "chat": "chat_completions",
        "chat_completion": "chat_completions",
        "chat_completions": "chat_completions",
        "responses": "responses",
    }
    try:
        return aliases[wire]
    except KeyError as exc:
        raise ValueError(
            "IDEASCIENTIST_WIRE_API must be 'chat_completions' or 'responses'"
        ) from exc


def _codex_auth_key(auth_file: Optional[str] = None) -> str:
    raw_path = (
        auth_file
        or os.environ.get("IDEASCIENTIST_CODEX_AUTH_FILE")
        or "~/.codex/auth.json"
    )
    path = Path(raw_path).expanduser()
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read Codex auth JSON from {path}") from exc
    key = data.get("OPENAI_API_KEY") if isinstance(data, dict) else None
    if not isinstance(key, str) or not key.strip():
        raise ValueError(f"Codex auth file {path} has no OPENAI_API_KEY")
    return key.strip()


def resolve_api_key(
    api_key: Optional[str] = None,
    *,
    wire_api: Optional[str] = None,
    require_key: bool = False,
) -> str:
    """Resolve an LLM key without changing the legacy local-chat behavior.

    Explicit and environment keys take precedence. Reading a Codex credential
    file requires a separate opt-in; selecting the Responses wire format alone
    must not send a local Codex credential to an arbitrary endpoint.
    """
    wire = normalize_wire_api(wire_api)
    explicit = (api_key or "").strip()
    if explicit and explicit != "EMPTY":
        return explicit

    key = _env_key("IDEASCIENTIST_API_KEY", "OPENAI_API_KEY")
    codex_opt_in = bool(os.environ.get("IDEASCIENTIST_CODEX_AUTH_FILE", "").strip()) or (
        os.environ.get("IDEASCIENTIST_USE_CODEX_AUTH", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if not key and wire == "responses" and codex_opt_in:
        key = _codex_auth_key()
    if require_key and not key:
        source = "IDEASCIENTIST_API_KEY or OPENAI_API_KEY"
        raise ValueError(f"No API key. Set {source}, or pass api_key=.")
    return key or "EMPTY"


def resolve_http_user_agent(
    wire_api: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """Use Codex's required UA in Responses mode; leave local chat untouched."""
    explicit = user_agent or os.environ.get("IDEASCIENTIST_HTTP_USER_AGENT", "")
    if explicit.strip():
        return explicit.strip()
    if normalize_wire_api(wire_api) == "responses":
        return DEFAULT_CODEX_USER_AGENT
    return ""


def request_headers(api_key: str, user_agent: str = "") -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


def responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate chat history into Responses input items."""
    items: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "tool":
            output = message.get("content")
            if not isinstance(output, str):
                output = json.dumps(output, ensure_ascii=False, default=str)
            items.append({
                "type": "function_call_output",
                "call_id": message.get("tool_call_id", ""),
                "output": output,
            })
            continue

        # Agentic responses retain the provider's original output items so
        # reasoning state and function calls can be sent back losslessly.
        prior_output = message.get("_responses_output")
        if role == "assistant" and isinstance(prior_output, list):
            items.extend(prior_output)
            continue

        content = message.get("content")
        if not isinstance(content, str):
            content = "" if content is None else str(content)
        if content or role != "assistant" or not message.get("tool_calls"):
            items.append({"role": role, "content": content})
        if role == "assistant":
            for tool_call in message.get("tool_calls") or []:
                fn = tool_call.get("function") or {}
                arguments = fn.get("arguments", "{}")
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments, ensure_ascii=False)
                items.append({
                    "type": "function_call",
                    "call_id": tool_call.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": arguments,
                })
    return items


def responses_tools(tools: Optional[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Translate Chat Completions function tools to Responses tool objects."""
    result: list[dict[str, Any]] = []
    for tool in tools or []:
        fn = tool.get("function", tool)
        converted = {
            "type": "function",
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
            # Existing harness schemas contain optional properties and do not
            # require additionalProperties:false. Responses otherwise defaults
            # to strict schema normalization, changing that contract.
            "strict": fn.get("strict", False),
        }
        result.append(converted)
    return result


def responses_payload(
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    tools: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build a stateless Responses request shared by every client entry point.

    Encrypted reasoning is needed when replaying output items after tool calls
    with store=False. Do not copy local vLLM chat-template parameters here.
    """
    payload: dict[str, Any] = {
        "model": model,
        "input": responses_input(messages),
        "max_output_tokens": max_tokens,
        "store": False,
        "stream": True,
        "include": ["reasoning.encrypted_content"],
    }
    effort = os.environ.get("IDEASCIENTIST_REASONING_EFFORT", "").strip()
    if effort:
        payload["reasoning"] = {"effort": effort}
    if tools:
        payload["tools"] = responses_tools(tools)
    return payload


class ResponsesAPIError(RuntimeError):
    """A failed or incomplete response, retaining usage for accurate logging."""

    def __init__(self, message: str, response: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.response = response or {}
        self.usage = _responses_usage(self.response.get("usage") or {})


def _responses_usage(raw_usage: dict[str, Any]) -> dict[str, Any]:
    return {
        **raw_usage,
        "prompt_tokens": raw_usage.get("input_tokens", raw_usage.get("prompt_tokens", 0)),
        "completion_tokens": raw_usage.get("output_tokens", raw_usage.get("completion_tokens", 0)),
    }


def normalize_responses_result(result: dict[str, Any]) -> dict[str, Any]:
    """Convert a Responses result to the Chat shape used by IdeaScientist."""
    if not isinstance(result, dict):
        raise ValueError("Responses API returned a non-object result")
    status = result.get("status")
    if result.get("error") or (status is not None and status != "completed"):
        detail = result.get("error") or result.get("incomplete_details") or status
        raise ResponsesAPIError(f"Responses API request did not complete: {detail}", result)

    content_parts: list[str] = []
    refusals: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for item in result.get("output") or []:
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    content_parts.append(part["text"])
                elif part.get("type") == "refusal" and isinstance(part.get("refusal"), str):
                    refusals.append(part["refusal"])
        elif item.get("type") == "function_call":
            if not item.get("call_id") or not item.get("name"):
                raise ResponsesAPIError("Responses function call lacks call_id or name", result)
            tool_calls.append({
                "id": item["call_id"],
                "type": "function",
                "function": {
                    "name": item.get("name", ""),
                    "arguments": item.get("arguments") or "{}",
                },
            })

    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(content_parts) or "".join(refusals),
        "_responses_output": result.get("output") or [],
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    if refusals:
        message["refusal"] = "".join(refusals)
    if not message["content"] and not tool_calls:
        raise ResponsesAPIError("Responses API returned no text or function call", result)
    usage = _responses_usage(result.get("usage") or {})
    return {
        "id": result.get("id", ""),
        "object": "chat.completion",
        "model": result.get("model", ""),
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": "tool_calls" if tool_calls else "stop",
        }],
        "usage": usage,
    }


def decode_responses_body(raw: bytes) -> dict[str, Any]:
    """Decode either a JSON Responses body or its terminal SSE event."""
    text = raw.decode("utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
        event_data: list[str] = []
        for line in text.splitlines() + [""]:
            if line.startswith("data:"):
                event_data.append(line[5:].lstrip())
                continue
            if line or not event_data:
                continue
            payload = "\n".join(event_data)
            event_data.clear()
            if payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                raise ResponsesAPIError("Responses SSE stream contained malformed JSON")
            if not isinstance(event, dict):
                raise ResponsesAPIError("Responses SSE event was not an object")
            event_type = event.get("type")
            if event_type == "error" or event.get("error"):
                detail = event.get("error") or event.get("message") or event.get("code")
                raise ResponsesAPIError(f"Responses SSE error: {detail}", event)
            if event_type in {
                "response.completed", "response.incomplete", "response.failed"
            } and isinstance(event.get("response"), dict):
                data = dict(event["response"])
                # Gate on the terminal event too, even if a gateway omits or
                # mislabels the status inside its response object.
                terminal_status = event_type.split(".", 1)[1]
                if terminal_status != "completed" or "status" not in data:
                    data["status"] = terminal_status
        if data is None:
            raise ResponsesAPIError("Responses SSE stream had no terminal response")
    return normalize_responses_result(data)


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    proxy: str = ""
    extra_body: Optional[dict[str, Any]] = None
    wire_api: str = DEFAULT_WIRE_API
    http_user_agent: str = ""

    @classmethod
    def from_env(
        cls,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        proxy: Optional[str] = None,
        require_key: bool = False,
    ) -> "LLMSettings":
        wire_api = normalize_wire_api()
        key = resolve_api_key(api_key, wire_api=wire_api, require_key=require_key)
        extra = os.environ.get("IDEASCIENTIST_EXTRA_BODY")
        return cls(
            api_key=key,
            base_url=(
                base_url
                or _env_key("IDEASCIENTIST_BASE_URL", "OPENAI_BASE_URL")
                or DEFAULT_BASE_URL
            ).rstrip("/"),
            model=model or os.environ.get("IDEASCIENTIST_MODEL") or DEFAULT_MODEL,
            proxy=proxy if proxy is not None else os.environ.get("HTTPS_PROXY_OVERRIDE", ""),
            extra_body=json.loads(extra) if extra else None,
            wire_api=wire_api,
            http_user_agent=resolve_http_user_agent(wire_api),
        )


@dataclass(frozen=True)
class EmbeddingSettings:
    api_key: str
    base_url: str = DEFAULT_EMBEDDING_BASE_URL
    model: str = DEFAULT_EMBEDDING_MODEL
    dim: int = DEFAULT_EMBEDDING_DIM
    proxy: str = ""

    @classmethod
    def from_env(
        cls,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        dim: Optional[int] = None,
        proxy: Optional[str] = None,
    ) -> "EmbeddingSettings":
        env_dim = os.environ.get("EMBEDDING_DIM")
        return cls(
            api_key=api_key or _env_key("EMBEDDING_API_KEY", "IDEASCIENTIST_API_KEY") or "EMPTY",
            base_url=(
                base_url or os.environ.get("EMBEDDING_BASE_URL") or DEFAULT_EMBEDDING_BASE_URL
            ).rstrip("/"),
            model=model or os.environ.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL,
            dim=dim if dim is not None else (int(env_dim) if env_dim else DEFAULT_EMBEDDING_DIM),
            proxy=proxy if proxy is not None else "",
        )


def chat_with_usage(
    messages: list[dict[str, str]],
    *,
    settings: Optional[LLMSettings] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: int = 4096,
    max_retries: int = 3,
    timeout: int = 120,
    total_deadline: Optional[float] = None,
    extra_body: Optional[dict[str, Any]] = None,
) -> tuple[str, dict[str, Any]]:
    """Chat completion returning ``(content, usage)``.

    ``timeout`` bounds one socket operation; ``total_deadline`` bounds the whole
    call including retries and backoff, so this never blocks a caller
    indefinitely on a stalled endpoint.
    """
    s = settings or LLMSettings.from_env()
    model = model or s.model
    wire_api = normalize_wire_api(s.wire_api)
    url = f"{s.base_url}/{'responses' if wire_api == 'responses' else 'chat/completions'}"

    env_to = os.environ.get("IDEASCIENTIST_SOCK_TIMEOUT", "").strip()
    if env_to:
        timeout = int(env_to)
    if total_deadline is None:
        env_dl = os.environ.get("IDEASCIENTIST_TOTAL_DEADLINE", "").strip()
        total_deadline = float(env_dl) if env_dl else max(timeout * 2, 240)

    if wire_api == "responses":
        payload = responses_payload(model, messages, max_tokens)
    else:
        payload = {"model": model, "messages": messages}
        if uses_completion_tokens(model):
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens
            if temperature is not None:
                payload["temperature"] = temperature
        if s.extra_body:
            payload.update(s.extra_body)
        if extra_body:
            payload.update(extra_body)

    body = json.dumps(payload).encode("utf-8")
    headers = request_headers(s.api_key, s.http_user_agent)
    # urllib openers are not documented thread-safe; build one per call.
    opener = build_opener(s.proxy)

    start = time.monotonic()
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        remaining = total_deadline - (time.monotonic() - start)
        if remaining <= 0:
            raise LLMTimeoutError(
                f"chat exceeded total deadline of {total_deadline:.0f}s "
                f"after {attempt} attempt(s): {last_exc}"
            )
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            raw = _open_with_deadline(
                opener, req, sock_timeout=min(timeout, remaining), deadline=remaining
            )
            result = (
                decode_responses_body(raw)
                if wire_api == "responses"
                else json.loads(raw.decode("utf-8"))
            )
            message = result["choices"][0]["message"]
            # A server running a reasoning parser returns ``content: null`` when
            # the reply is truncated inside the reasoning block. Callers parse
            # text, so hand back the reasoning rather than None.
            content = message.get("content")
            if not content:
                content = message.get("reasoning_content") or ""
            return content, result.get("usage", {})
        except LLMTimeoutError:
            raise
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last_exc = e
            retryable = not isinstance(e, urllib.error.HTTPError) or e.code in _RETRYABLE_STATUS
            if not retryable or attempt >= max_retries:
                raise
            budget = total_deadline - (time.monotonic() - start)
            if budget <= 0:
                raise
            time.sleep(min(2 ** (attempt + 1), 30, budget))
    raise RuntimeError(f"chat failed after {max_retries + 1} attempts: {last_exc}")


def chat(messages: list[dict[str, str]], **kwargs: Any) -> str:
    return chat_with_usage(messages, **kwargs)[0]


def complete(prompt: str, *, system: Optional[str] = None, **kwargs: Any) -> str:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return chat(messages, **kwargs)


def embed_texts(
    texts: list[str],
    *,
    settings: Optional[EmbeddingSettings] = None,
    model: Optional[str] = None,
    dimensions: Optional[int] = None,
    max_input_chars: int = 8000,
    max_retries: int = 3,
    timeout: int = 60,
) -> list[list[float]]:
    """Embed a batch of texts, preserving input order."""
    s = settings or EmbeddingSettings.from_env()
    url = f"{s.base_url}/embeddings"
    headers = {"Authorization": f"Bearer {s.api_key}", "Content-Type": "application/json"}
    body = json.dumps(
        {
            "input": [t[:max_input_chars] for t in texts],
            "model": model or s.model,
            "dimensions": dimensions if dimensions is not None else s.dim,
        }
    ).encode("utf-8")
    opener = build_opener(s.proxy)

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with opener.open(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return [d["embedding"] for d in sorted(result["data"], key=lambda x: x["index"])]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last_exc = e
            retryable = not isinstance(e, urllib.error.HTTPError) or e.code in _RETRYABLE_STATUS
            if not retryable or attempt >= max_retries:
                raise
            time.sleep(min(2 ** (attempt + 1), 30))
    raise RuntimeError(f"embed failed after {max_retries + 1} attempts: {last_exc}")


def embed_text(text: str, **kwargs: Any) -> list[float]:
    return embed_texts([text], **kwargs)[0]
