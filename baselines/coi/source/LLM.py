"""CoI transport adapter: explicit protocol, bounded retries, secret-free audit log."""
import asyncio
import base64
import json
import hashlib
import os
import random
import time
import uuid
from pathlib import Path
import httpx
import numpy as np


def get_content_between_a_b(start_tag, end_tag, text):
    pieces = []
    while start_tag in text:
        _, _, rest = text.partition(start_tag)
        part, end, text = rest.partition(end_tag)
        if not end:
            break
        pieces.append(part)
    return " ".join(pieces).strip()


def encode_image(image_path):
    return base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")


def get_openai_url(img_pth):
    ext = Path(img_pth).suffix.lstrip(".").replace("jpg", "jpeg")
    return f"data:image/{ext};base64,{encode_image(img_pth)}"


class base_llm:
    pass


class TransientGatewayError(RuntimeError):
    pass


class OutputLimitError(RuntimeError):
    pass


class GatewayPolicyError(RuntimeError):
    pass


class ModelMismatchError(RuntimeError):
    """The gateway returned a model different from the requested model."""
    def __init__(self, requested, reported, source="response"):
        self.requested = requested
        self.reported = reported
        self.source = source
        super().__init__(f"model_mismatch:{source}:requested={requested!r}:reported={reported!r}")


class SSEDecoder:
    """Only a complete terminal response is usable; deltas never imply success."""
    def __init__(self):
        self.parts = []

    def feed(self, line):
        if not line.strip():
            return self.flush()
        if line.startswith("data:"):
            self.parts.append(line[5:].lstrip())
        return None

    def flush(self):
        if not self.parts:
            return None
        raw = "\n".join(self.parts)
        self.parts = []
        if raw.strip() == "[DONE]":
            return None
        try:
            event = json.loads(raw)
        except ValueError:
            raise TransientGatewayError("malformed_sse_event") from None
        if not isinstance(event, dict):
            raise TransientGatewayError("invalid_sse_event")
        if event.get("type") == "error":
            return {"status": "failed", "error": event.get("error") or event}
        if event.get("type") in {"response.completed", "response.incomplete", "response.failed"}:
            data = event.get("response")
            if not isinstance(data, dict):
                raise TransientGatewayError("invalid_terminal_sse")
            return data
        return None


class openai_llm(base_llm):
    def __init__(self, model="gpt4o-0513"):
        self.model = model
        self.is_azure = str(os.environ.get("is_azure", "false")).lower() in {"1", "true", "yes"}
        self.require_model_match = str(os.environ.get("COI_REQUIRE_MODEL_MATCH", "false")).lower() in {"1", "true", "yes"}
        self.wire_api = os.environ.get("OPENAI_WIRE_API", "chat")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.key = os.environ.get("OPENAI_API_KEY", "")
        if self.wire_api == "anthropic":
            self.base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
            if not self.base_url.endswith("/v1"):
                self.base_url += "/v1"
            self.key = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
        if self.is_azure:
            raise ValueError("This deployment uses a non-Azure endpoint; set is_azure=false")
        if not self.key or self.key.startswith("${"):
            raise ValueError("Model provider credential is not set to a real environment credential")
        self.headers = {"Authorization": "Bearer " + self.key,
                        "User-Agent": os.environ.get("COI_HTTP_USER_AGENT", "codex_cli_rs/0.114.0")}
        if self.wire_api == "anthropic":
            self.headers.update({"x-api-key": self.key, "anthropic-version": "2023-06-01", "x-app": "cli",
                                 "User-Agent": os.environ.get("COI_HTTP_USER_AGENT", "claude-cli/2.1.304 (external, sdk-cli)")})

    def _payload(self, messages, kwargs):
        instruction = ("\n\nDeployment output requirements: preserve the requested XML tags and JSON schemas exactly. "
                       "Write research prose, final ideas, and experiment plans in Chinese; keep search queries, "
                       "paper titles and reference lists in their original English. Propose experiments only; "
                       "do not execute them or claim measured results. Do not invent citations. "
                       "Security experiments must be limited to authorized isolated benchmarks or synthetic "
                       "environments; do not propose operating real third-party accounts or services. "
                       "A novelty check is a limited search, not proof of novelty. Do not reveal hidden chain-of-thought "
                       "or private deliberation; provide concise externally checkable summaries and the requested final fields.")
        adapted = [dict(m) for m in messages]
        if self.wire_api == "anthropic":
            # Upstream does not consume <think>. Use an ordinary explanation
            # field, separate from the API's private thinking channel.
            for message in adapted:
                message["content"] = (message["content"].replace("<think>", "<rationale>")
                    .replace("</think>", "</rationale>")
                    .replace("your thinking steps", "a brief externally checkable justification")
                    .replace("Here is your thinking steps:", "Cover these points in your concise explanation:")
                    .replace("There are my think steps:", "Concise justification:"))
        adapted[-1] = {**adapted[-1], "content": adapted[-1]["content"] + instruction}
        model = kwargs.get("model", self.model)
        if self.wire_api == "anthropic":
            payload = {"model": model, "messages": [m for m in adapted if m["role"] != "system"],
                       "max_tokens": max(8192, kwargs.get("max_tokens", 4000)), "stream": True,
                       "thinking": {"type": "adaptive"},
                       "output_config": {"effort": os.environ.get("COI_REASONING_EFFORT", "high")}}
            system = "\n\n".join(m["content"] for m in adapted if m["role"] == "system")
            if system:
                payload["system"] = system
            return "/messages", payload
        if self.wire_api == "responses":
            return "/responses", {"model": model, "input": adapted,
                # Responses counts reasoning in this budget, while upstream's
                # Chat limit was used for the visible research text.
                "max_output_tokens": max(8192, kwargs.get("max_tokens", 4000)),
                "store": False, "stream": True,
                "reasoning": {"effort": os.environ.get("COI_REASONING_EFFORT", "medium")}}
        return "/chat/completions", {"model": model, "messages": adapted,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4000), "stream": False}

    def _check_model_match(self, data, requested_model, source="response"):
        if not self.require_model_match:
            return
        reported_model = data.get("model") if isinstance(data, dict) else None
        if reported_model == requested_model:
            return
        self._log_model_mismatch(requested_model, reported_model, source)
        raise ModelMismatchError(requested_model, reported_model, source)

    def _log_model_mismatch(self, requested_model, reported_model, source):
        path = Path(os.environ.get("COI_API_LOG", "api_calls.jsonl"))
        row = {"time": time.time(), "event": "model_mismatch", "source": source,
               "model_requested": requested_model, "model_reported": reported_model,
               "wire_api": self.wire_api}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _decode_data(self, data, requested_model=None):
        if not isinstance(data, dict):
            raise TransientGatewayError("invalid_response_object")
        if data.get("error") or data.get("status") in {"failed", "incomplete"}:
            error = data.get("error") or data.get("incomplete_details") or {}
            code = error.get("code") or error.get("type")
            if code in {"invalid_prompt", "content_policy_violation"} or error.get("reason") == "content_filter":
                raise GatewayPolicyError("gateway_policy_rejection")
            if error.get("reason") == "max_output_tokens":
                raise OutputLimitError("Responses output budget exhausted")
            if code in {"upstream_error", "server_error", "rate_limit_exceeded", "overloaded"}:
                raise TransientGatewayError("gateway_" + code)
            # A terminal failed response without a known policy/limit code is normally
            # an upstream failure. Retry it without persisting the provider's raw message.
            raise TransientGatewayError("gateway_failed_response")
        self._check_model_match(data, requested_model or self.model)
        if self.wire_api == "responses":
            if data.get("status") != "completed":
                raise TransientGatewayError("response_not_completed")
            content = "".join(part.get("text", "") for item in data.get("output", [])
                              if item.get("type") == "message" for part in item.get("content", [])
                              if part.get("type") == "output_text")
        else:
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise OutputLimitError("Chat output budget exhausted")
            content = choice["message"]["content"]
        if not content or not content.strip():
            raise TransientGatewayError("empty_completed_response")
        return content, data

    def _decode(self, response, requested_model=None):
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError:
            data, decoder = None, SSEDecoder()
            for line in response.text.splitlines():
                data = decoder.feed(line)
                if data is not None:
                    break
            if data is None:
                data = decoder.flush()
            if data is None:
                raise TransientGatewayError("missing_final_sse")
        return self._decode_data(data, requested_model=requested_model)

    async def _request(self, client, endpoint, payload):
        if self.wire_api == "anthropic":
            from LLM_anthropic import request_anthropic
            content, data = await request_anthropic(client, self.base_url, payload)
            self._check_model_match(data, payload.get("model", self.model))
            return content, data
        async with client.stream("POST", self.base_url + endpoint, json=payload) as response:
            if response.is_error:
                # Status/headers suffice for retries; never log the credential-bearing request.
                if response.status_code in {400, 403, 422}:
                    await response.aread()
                    try:
                        error = response.json().get("error") or {}
                    except (ValueError, AttributeError):
                        error = {}
                    if error.get("code") in {"invalid_prompt", "content_policy_violation"}:
                        raise GatewayPolicyError("gateway_policy_rejection")
                response.raise_for_status()
            if "text/event-stream" not in response.headers.get("content-type", "").lower():
                await response.aread()
                return self._decode(response, requested_model=payload.get("model"))
            decoder, data = SSEDecoder(), None
            try:
                async for line in response.aiter_lines():
                    if data is None:
                        data = decoder.feed(line)
                    # Drain the stream after the terminal event. Prematurely closing nested
                    # HTTPX iterators under upstream's nest_asyncio can leak generators.
            except httpx.TransportError:
                if data is None:
                    raise
                # A proxy reset after a complete terminal object does not invalidate it.
            if data is None:
                data = decoder.flush()
            if data is not None:
                return self._decode_data(data, requested_model=payload.get("model"))
            raise TransientGatewayError("missing_final_sse")

    def _retry_log(self, attempt, category, delay, exhausted, started, cache_key):
        row = {"time": time.time(), "event": "request_retry", "attempt": attempt,
               "category": category, "retry_delay_seconds": round(delay, 3),
               "exhausted": exhausted, "elapsed_seconds": round(time.monotonic() - started, 3),
               "model_requested": self.model, "cache_key": cache_key}
        with Path(os.environ.get("COI_API_LOG", "api_calls.jsonl")).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def _log(self, messages, data, started, payload):
        path = Path(os.environ.get("COI_API_LOG", "api_calls.jsonl"))
        row = {"time": time.time(), "elapsed_seconds": round(time.monotonic() - started, 3),
               "model_requested": payload.get("model", self.model), "model_reported": data.get("model"),
               "wire_api": self.wire_api, "response_id": data.get("id"),
               "usage": data.get("usage"), "input_characters": sum(len(m.get("content", "")) for m in messages),
               "requested_max_output_tokens": payload.get("max_output_tokens", payload.get("max_tokens")),
               "reported_max_output_tokens": data.get("max_output_tokens"),
               "reasoning_requested": payload.get("reasoning") or payload.get("output_config"),
               "thinking_requested": payload.get("thinking"),
               "gateway_restart_count": data.get("gateway_restart_count", 0)}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    async def response_async(self, messages, **kwargs):
        endpoint, payload = self._payload(messages, kwargs)
        cache_dir = Path(".llm_cache")
        cache_dir.mkdir(exist_ok=True)
        cache_key = hashlib.sha256(json.dumps({"endpoint": endpoint, "base_url": self.base_url,
            "payload": payload}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cache_file = cache_dir / (cache_key + ".json")
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cached = {}
            if cached.get("content"):
                if self.require_model_match:
                    requested_model = payload.get("model", self.model)
                    reported_model = cached.get("model_reported")
                    if cached.get("model_requested") != requested_model or reported_model != requested_model:
                        self._log_model_mismatch(requested_model, reported_model, "cache")
                        raise ModelMismatchError(requested_model, reported_model, "cache")
                with Path(os.environ.get("COI_API_LOG", "api_calls.jsonl")).open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"time": time.time(), "event": "same_task_response_cache_hit",
                        "model_requested": payload.get("model", self.model),
                        "model_reported": cached.get("model_reported"),
                        "cache_key": cache_key, "usage": None}) + "\n")
                return cached["content"]
        max_attempts = max(1, min(16, int(os.environ.get("COI_REQUEST_ATTEMPTS", "12"))))
        try:
            retry_base = max(1.0, float(os.environ.get("COI_RETRY_BASE_SECONDS", "10")))
            retry_cap = max(retry_base, float(os.environ.get("COI_RETRY_MAX_SECONDS", "180")))
            request_timeout = max(30.0, float(os.environ.get("COI_LLM_TIMEOUT_SECONDS", "420")))
            connect_timeout = max(5.0, float(os.environ.get("COI_CONNECT_TIMEOUT_SECONDS", "30")))
        except ValueError:
            retry_base, retry_cap, request_timeout, connect_timeout = 10.0, 180.0, 420.0, 30.0
        for attempt in range(max_attempts):
            retry_after = 0
            started = time.monotonic()
            try:
                # Upstream invokes asyncio.run repeatedly: avoid sharing a client across loops.
                timeout = kwargs.get("timeout")
                if timeout is None:
                    timeout = httpx.Timeout(request_timeout, connect=connect_timeout, pool=connect_timeout)
                async with httpx.AsyncClient(headers=self.headers, timeout=timeout) as client:
                    content, data = await self._request(client, endpoint, payload)
                self._log(messages, data, started, payload)
                temporary = cache_file.with_suffix("." + uuid.uuid4().hex + ".tmp")
                temporary.write_text(json.dumps({"content": content, "response_id": data.get("id"),
                    "model_requested": payload.get("model", self.model),
                    "model_reported": data.get("model")}, ensure_ascii=False), encoding="utf-8")
                temporary.replace(cache_file)
                return content
            except OutputLimitError:
                budget_key = "max_output_tokens" if self.wire_api == "responses" else "max_tokens"
                if attempt == max_attempts - 1 or payload.get(budget_key, 0) >= 32768:
                    raise
                payload[budget_key] = min(32768, payload[budget_key] * 2)
                category = "output_limit"
            except httpx.HTTPStatusError as e:
                if e.response.status_code not in {408, 429, 500, 502, 503, 504, 520, 522, 524, 529}:
                    raise RuntimeError(f"Model gateway HTTP {e.response.status_code}; see deployment diagnostics") from None
                category = "http_" + str(e.response.status_code)
                try:
                    retry_after = min(120, max(0, float(e.response.headers.get("retry-after", "0"))))
                except ValueError:
                    pass
            except (httpx.TransportError, TransientGatewayError) as e:
                category = str(e) if isinstance(e, TransientGatewayError) else type(e).__name__
            exhausted = attempt == max_attempts - 1
            delay = 0 if exhausted else max(retry_after, min(retry_cap, retry_base * 2 ** attempt) + random.uniform(0, 4))
            self._retry_log(attempt + 1, category, delay, exhausted, started, cache_key)
            if exhausted:
                raise TransientGatewayError("request_attempts_exhausted:" + category) from None
            await asyncio.sleep(delay)

    def response(self, messages, **kwargs):
        return asyncio.run(self.response_async(messages, **kwargs))

    def get_embbeding(self, text):
        with httpx.Client(headers=self.headers, timeout=90) as client:
            response = client.post(self.base_url + "/embeddings", json={
                "model": os.environ.get("EMBEDDING_MODEL") or "text-embedding-3-large", "input": text})
        response.raise_for_status()
        vectors = [item["embedding"] for item in response.json()["data"]]
        return vectors if isinstance(text, list) else vectors[0]

    async def get_embbeding_async(self, text):
        return await asyncio.to_thread(self.get_embbeding, text)

    def cal_cosine_similarity(self, vec1, vec2):
        a, b = np.asarray(vec1), np.asarray(vec2)
        return np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12)
