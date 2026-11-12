"""Strict Anthropic Messages transport; hidden thinking is never retained."""
import json

import httpx


def _errors():
    from LLM import GatewayPolicyError, OutputLimitError, TransientGatewayError
    return GatewayPolicyError, OutputLimitError, TransientGatewayError


def _fail(reason):
    raise _errors()[2]("anthropic_" + reason)


def _provider_error(error):
    policy_error, output_error, transient_error = _errors()
    error = error if isinstance(error, dict) else {}
    category = error.get("type") or error.get("code")
    if category in {"refusal", "content_policy_violation", "content_filter", "invalid_prompt", "safety_error", "policy_error"}:
        raise policy_error("anthropic_policy_rejection")
    if category in {"max_tokens", "max_output_tokens"}:
        raise output_error("Anthropic output budget exhausted")
    # Raw provider messages can contain request fragments. Do not expose them.
    raise transient_error("anthropic_provider_error")


def _merge_usage(previous, incoming):
    if not isinstance(incoming, dict):
        _fail("invalid_usage")
    result = dict(previous)
    for name, value in incoming.items():
        if isinstance(value, dict):
            result[name] = _merge_usage(result.get(name, {}), value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            # Anthropic usage values are cumulative, including message_delta's
            # output_tokens; adding initial and final values double counts them.
            result[name] = value
        elif value is None or isinstance(value, str):
            result[name] = value
        else:
            _fail("invalid_usage_value")
    return result


def _finish(message):
    if not isinstance(message, dict):
        _fail("invalid_message")
    if message.get("type") == "error" or message.get("error"):
        _provider_error(message.get("error"))
    if message.get("type") != "message":
        _fail("invalid_message_type")
    policy_error, output_error, _ = _errors()
    reason = message.get("stop_reason")
    if reason == "max_tokens":
        raise output_error("Anthropic output budget exhausted")
    if reason in {"refusal", "content_filter", "content_policy_violation", "safety"}:
        raise policy_error("anthropic_policy_rejection")
    if reason not in {"end_turn", "stop_sequence"}:
        _fail("invalid_stop_reason")
    blocks = message.get("content")
    if not isinstance(blocks, list):
        _fail("invalid_content")
    clean_blocks, pieces = [], []
    for block in blocks:
        if not isinstance(block, dict) or not isinstance(block.get("type"), str):
            _fail("invalid_content_block")
        if block["type"] == "text":
            text = block.get("text")
            if not isinstance(text, str):
                _fail("invalid_text_block")
            clean_blocks.append({"type": "text", "text": text})
            pieces.append(text)
        elif block["type"] == "refusal":
            raise policy_error("anthropic_policy_rejection")
        elif block["type"] == "fallback":
            raise RuntimeError("anthropic_unexpected_model_fallback")
        # Do not return or cache thinking, signatures or redacted thinking data.
    content = "".join(pieces)
    if not content.strip():
        _fail("empty_completed_message")
    clean = {name: message.get(name) for name in ("id", "type", "role", "model", "stop_reason", "stop_sequence")}
    clean["content"] = clean_blocks
    clean["usage"] = _merge_usage({}, message.get("usage") or {})
    clean["gateway_restart_count"] = message.get("gateway_restart_count", 0)
    return content, clean


class _MessagesStream:
    def __init__(self):
        self.message = None
        self.blocks = {}
        self.stopped = False
        self.gateway_restart_count = 0

    def event(self, data, event_name=None):
        if not isinstance(data, dict):
            _fail("invalid_sse_event")
        kind = data.get("type")
        if not isinstance(kind, str) or (event_name and event_name != kind):
            _fail("invalid_sse_event_type")
        if kind == "ping":
            return
        if kind == "error":
            _provider_error(data.get("error"))
        if self.stopped:
            _fail("event_after_message_stop")
        if kind == "message_start":
            message = data.get("message")
            if not isinstance(message, dict) or message.get("type") != "message" or message.get("content") != []:
                _fail("invalid_message_start")
            if self.message is not None:
                if (self.blocks or self.message.get("stop_reason") is not None
                        or self.message.get("stop_sequence") is not None):
                    _fail("message_restart_after_content")
                if message.get("model") != self.message.get("model"):
                    _fail("message_restart_model_changed")
                if message.get("stop_reason") is not None or message.get("stop_sequence") is not None:
                    _fail("invalid_message_restart")
                if self.gateway_restart_count >= 16:
                    _fail("message_restart_limit")
                # This gateway can restart an empty upstream attempt within one
                # SSE stream. No text or completion is accepted from the prelude.
                self.gateway_restart_count += 1
            self.message = {name: message.get(name) for name in ("id", "type", "role", "model", "stop_reason", "stop_sequence")}
            self.message["usage"] = _merge_usage({}, message.get("usage") or {})
            return
        known = {"content_block_start", "content_block_delta", "content_block_stop", "message_delta", "message_stop"}
        if kind not in known:
            # Anthropic may add new SSE event types. They cannot supply text or
            # replace the required message/block completion events.
            return
        if self.message is None:
            _fail("event_before_message_start")
        if kind.startswith("content_block_"):
            index = data.get("index")
            if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                _fail("invalid_block_index")
            if kind == "content_block_start":
                block = data.get("content_block")
                if index in self.blocks or not isinstance(block, dict) or not isinstance(block.get("type"), str):
                    _fail("invalid_block_start")
                block_type = block["type"]
                if block_type == "fallback":
                    raise RuntimeError("anthropic_unexpected_model_fallback")
                parts = []
                if block_type == "text":
                    if not isinstance(block.get("text"), str):
                        _fail("invalid_text_start")
                    parts.append(block["text"])
                self.blocks[index] = {"type": block_type, "closed": False, "parts": parts}
                return
            block = self.blocks.get(index)
            if not block or block["closed"]:
                _fail("invalid_block_transition")
            if kind == "content_block_stop":
                block["closed"] = True
                return
            delta = data.get("delta")
            if not isinstance(delta, dict) or not isinstance(delta.get("type"), str):
                _fail("invalid_block_delta")
            if delta["type"] == "text_delta":
                if block["type"] != "text" or not isinstance(delta.get("text"), str):
                    _fail("invalid_text_delta")
                block["parts"].append(delta["text"])
            elif delta["type"] in {"thinking_delta", "signature_delta"}:
                field = "thinking" if delta["type"] == "thinking_delta" else "signature"
                if block["type"] != "thinking" or not isinstance(delta.get(field), str):
                    _fail("invalid_thinking_delta")
                # Never retain or print hidden thinking, including signatures.
            elif delta["type"] == "input_json_delta" and block["type"] not in {"tool_use", "server_tool_use"}:
                _fail("invalid_tool_delta")
            return
        if kind == "message_delta":
            delta = data.get("delta")
            if not isinstance(delta, dict):
                _fail("invalid_message_delta")
            for name in ("stop_reason", "stop_sequence", "model"):
                if name in delta:
                    self.message[name] = delta[name]
            if "usage" in data:
                self.message["usage"] = _merge_usage(self.message["usage"], data["usage"])
            return
        if kind == "message_stop":
            if any(not block["closed"] for block in self.blocks.values()):
                _fail("unclosed_content_block")
            self.stopped = True

    def finish(self):
        if not self.stopped or self.message is None:
            _fail("missing_message_stop")
        message = dict(self.message)
        message["gateway_restart_count"] = self.gateway_restart_count
        message["content"] = [{"type": block["type"], "text": "".join(block["parts"])}
                              for _, block in sorted(self.blocks.items())]
        return _finish(message)


async def request_anthropic(client, base_url, payload):
    """Return visible text and sanitized final message; HTTP errors remain HTTPX errors."""
    async with client.stream("POST", base_url.rstrip("/") + "/messages", json=payload) as response:
        if response.status_code in {400, 403, 422}:
            await response.aread()
            try:
                error = response.json().get("error") or {}
            except (ValueError, AttributeError):
                error = {}
            if isinstance(error, dict) and (error.get("type") or error.get("code")) in {"refusal", "content_policy_violation", "content_filter", "invalid_prompt", "safety_error", "policy_error"}:
                _provider_error(error)
        response.raise_for_status()
        if "text/event-stream" not in response.headers.get("content-type", "").lower():
            await response.aread()
            try:
                data = response.json()
            except (ValueError, UnicodeError):
                _fail("malformed_json_response")
            return _finish(data)
        stream, lines, event_name = _MessagesStream(), [], None
        pending_error = None
        def remember_error(error):
            nonlocal pending_error
            policy_error = _errors()[0]
            if pending_error is None or (isinstance(error, policy_error) and not isinstance(pending_error, policy_error)):
                pending_error = error
        def dispatch():
            nonlocal lines, event_name
            try:
                if lines:
                    data = json.loads("\n".join(lines))
                    # Detect explicit policy events even when an earlier malformed
                    # event left parser state unusable. Policy errors take priority.
                    if isinstance(data, dict):
                        delta = data.get("delta")
                        block = data.get("content_block")
                        if ((isinstance(delta, dict) and delta.get("stop_reason") in {"refusal", "content_filter", "content_policy_violation", "safety"})
                                or (isinstance(block, dict) and block.get("type") == "refusal")):
                            raise _errors()[0]("anthropic_policy_rejection")
                    stream.event(data, event_name)
                elif event_name:
                    _fail("missing_sse_data")
            except (ValueError, UnicodeError):
                remember_error(_errors()[2]("anthropic_malformed_sse_json"))
            except Exception as error:
                remember_error(error)
            finally:
                lines, event_name = [], None
        try:
            async for line in response.aiter_lines():
                if line == "":
                    dispatch()
                elif line.startswith(":"):
                    continue
                elif line.startswith("data:"):
                    value = line[5:]
                    lines.append(value[1:] if value.startswith(" ") else value)
                elif line.startswith("event:"):
                    event_name = line[6:].strip()
                # SSE id/retry and unknown fields are permitted by the protocol.
        except httpx.TransportError:
            remember_error(_errors()[2]("anthropic_interrupted_sse_stream"))
        if lines or event_name:
            # An unterminated SSE event is a truncated stream, even if its JSON
            # happens to be parseable. message_stop must have a blank delimiter.
            remember_error(_errors()[2]("anthropic_unterminated_sse_event"))
        # Drain before raising parser errors so HTTPX/nest_asyncio do not abandon
        # nested async generators. A complete later event cannot erase an error.
        if pending_error is not None:
            raise pending_error
        return stream.finish()
