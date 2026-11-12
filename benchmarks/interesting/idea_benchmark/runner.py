"""Responses API execution with immutable attempts, resumability, and measured usage."""
import concurrent.futures
import fcntl
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from .core import (canonical, now, read_json, save_json, sha, usage_cost, normalize_assessment_envelope, derive_assessment_scores,
                   validate_assessment, verify_batch, parse_assessment_json)


def credentials(use_codex_auth=False):
    if use_codex_auth:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        config = tomllib.loads((home / "config.toml").read_text())
        provider = config.get("model_provider", "openai")
        spec = config.get("model_providers", {}).get(provider, {})
        base = spec.get("base_url", "https://api.openai.com/v1")
        key = os.environ.get(spec.get("env_key", ""))
        if not key:
            key = read_json(home / "auth.json").get("OPENAI_API_KEY")
    else:
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("No API key. Set OPENAI_API_KEY or explicitly use --use-codex-auth")
    url = urlparse(base)
    if url.scheme != "https" or url.username or url.password or url.query:
        raise ValueError("An HTTPS API endpoint without embedded credentials is required")
    return base.rstrip("/"), key


def request_payload(model, prompt, packet, config):
    return {
        "model": model, "instructions": prompt,
        "input": [{"role": "user", "content": [{"type": "input_text",
            "text": json.dumps(packet, ensure_ascii=False)}]}],
        "reasoning": {"effort": config["reasoning_effort"]},
        "max_output_tokens": config["max_output_tokens"],
        "text": {"format": {"type": "json_object"}},
        "store": False, "stream": True, "service_tier": config["service_tier"],
    }


def codex_command(model, effort="medium"):
    """Build the same Codex CLI command as IdeaX's gpt_transport adapter.

    IdeaX deliberately lets Codex own authentication and provider transport. The
    benchmark must use that path too; copying an API key into requests.py bypasses
    the working transport and is what caused the Cloudflare 403.
    """
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    config = tomllib.loads((home / "config.toml").read_text())
    provider = config.get("model_provider", "OpenAI")
    spec = config.get("model_providers", {}).get(provider, {})
    args = [os.environ.get("AUTORESEARCH_CODEX_BIN", "codex"), "exec", "--json",
            "--skip-git-repo-check", "--sandbox", "read-only", "--model", model,
            "-c", 'model_reasoning_effort=' + json.dumps(effort),
            "-c", 'approval_policy="never"', "--ignore-user-config",
            "-c", 'features.multi_agent=false',
            "-c", 'model_provider=' + json.dumps(provider)]
    # gpt_transport.py copies these fields into CLI -c overrides. This is the
    # important part: Codex reads auth from CODEX_HOME and handles the gateway.
    for key_name in ("name", "base_url", "wire_api", "requires_openai_auth", "env_key"):
        if key_name in spec:
            args += ["-c", f"model_providers.{provider}.{key_name}=" + json.dumps(spec[key_name])]
    return args + ["-"]


def normalize_codex_usage(usage):
    if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
        raise ValueError("CLI did not report valid input/output usage")
    result = {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
              "input_tokens_details": {}, "output_tokens_details": {}}
    for source, group, name in (("cached_input_tokens", "input_tokens_details", "cached_tokens"),
                                ("cache_write_input_tokens", "input_tokens_details", "cache_write_tokens"),
                                ("reasoning_output_tokens", "output_tokens_details", "reasoning_tokens")):
        if source in usage:
            if type(usage[source]) is not int or usage[source] < 0:
                raise ValueError(f"Invalid CLI usage field: {source}")
            result[group][name] = usage[source]
    return result


def call_codex(model, prompt, packet, attempt, config):
    """Run Codex exactly through its JSONL event transport and normalize usage."""
    command = codex_command(model, config["reasoning_effort"])
    payload = json.dumps(packet, ensure_ascii=False)
    full_prompt = prompt + "\n\n## Current item (JSON)\n" + payload
    save_json(attempt / "codex_command.json", {"command": command[:-1] + ["-"],
                                                "transport": "codex-cli", "prompt_sha256": sha(full_prompt.encode())})
    env = os.environ.copy()
    # Do not leak direct API credentials into the child; Codex authenticates via
    # CODEX_HOME just as IdeaX does.
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        env.pop(key, None)
    (attempt / "codex_prompt.md").write_text(full_prompt)
    events = []
    final_text, usage, thread_id, failure = "", None, None, None
    with (attempt / "codex.stdout.jsonl").open("wb") as out, (attempt / "codex.stderr.log").open("wb") as err:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, cwd=attempt, env=env,
                                   stdout=out, stderr=err, start_new_session=True)
        save_json(attempt / "process.json", {"pid": process.pid, "started_at": now()})
        try:
            process.communicate(full_prompt.encode(), timeout=config["timeout_seconds"] + 30)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise RuntimeError("Codex CLI timeout; no automatic retry because completion is indeterminate") from exc
    stdout = (attempt / "codex.stdout.jsonl").read_text(errors="replace")
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(event)
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        elif event.get("type") == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                final_text = str(item.get("text", ""))
        elif event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
        elif event.get("type") == "turn.failed":
            failure = str(event.get("error", "turn failed"))
    if process.returncode != 0 or failure or not final_text or usage is None:
        detail = failure or (attempt / "codex.stderr.log").read_text(errors="replace")[-1000:]
        raise RuntimeError(f"Codex CLI failed ({process.returncode}): {detail}")
    # IdeaX's turn usage uses flattened cached/reasoning fields. Normalize into
    # the Responses usage shape consumed by the accounting/report code.
    normalized = normalize_codex_usage(usage)
    result = {"id": thread_id or "codex-cli", "status": "completed", "model": model,
            "output": [{"type": "message", "content": [{"type": "output_text", "text": final_text}]}],
            "usage": normalized, "service_tier": "default", "codex_usage": usage,
            "events_count": len(events), "model_identity_source": "CLI --model argument; upstream identity not independently exposed",
            "tool_calls": [e['item'].get('type') for e in events if e.get('type') == 'item.completed'
                           and e.get('item', {}).get('type') not in ('agent_message', 'reasoning')]}
    save_json(attempt / "response.json", result)
    return result


def call_response(base, key, payload, attempt, timeout):
    """Record SSE durably; do not follow redirects carrying the API credential."""
    with requests.post(base + "/responses", json=payload,
                       headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                       stream=True, timeout=(30, timeout), allow_redirects=False) as response:
        if response.status_code != 200:
            body = response.text[:2000].replace(key, "[REDACTED]")
            headers = {k: response.headers[k] for k in
                       ("content-type", "server", "cf-mitigated", "cf-ray", "x-request-id", "retry-after")
                       if k in response.headers}
            save_json(attempt / "http_error.json", {"status": response.status_code, "body": body, "headers": headers})
            if response.headers.get("cf-mitigated") == "challenge":
                raise RuntimeError(f"HTTP {response.status_code}: Cloudflare challenge blocks API access; gateway administrator action required")
            raise RuntimeError(f"HTTP {response.status_code}: {body[:500]}")
        if "text/event-stream" not in response.headers.get("content-type", ""):
            result = response.json()
            save_json(attempt / "response.json", result)
            return result
        final = None
        with (attempt / "events.jsonl").open("w") as handle:
            for line in response.iter_lines():
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    continue
                event = json.loads(data)
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
                handle.flush()
                if event.get("type") in ("response.completed", "response.incomplete", "response.failed"):
                    final = event["response"]
                    save_json(attempt / "response.json", final)
        if final is None:
            raise RuntimeError("Stream ended without terminal response; token usage unknown")
        return final


def extract_text(response):
    return "".join(c.get("text", "") for item in response.get("output", [])
                   if item.get("type") == "message" for c in item.get("content", [])
                   if c.get("type") == "output_text")


def finalize(attempt, response, packet, mapping, batch, model, config, record):
    record["returned_model"] = response.get("model")
    record["response_id"] = response.get("id")
    record["response_status"] = response.get("status")
    record["model_identity_source"] = response.get("model_identity_source", "API response model field")
    record["usage"] = response.get("usage")
    returned = response.get("model", "")
    price_model = model if returned == model or re.fullmatch(re.escape(model) + r"-\d{4}-\d{2}-\d{2}", returned) else returned
    record["cost"] = usage_cost(response.get("usage"), price_model, config, response.get("service_tier", "default"))
    # Persist measured usage before validating semantic output; failed reviews still cost money.
    save_json(attempt / "record.json", record)
    if response.get("status") != "completed":
        raise ValueError(f"Incomplete response: {response.get('status')}")
    if response.get("tool_calls"):
        raise ValueError(f"Unexpected tool use under provided-material-only protocol: {response['tool_calls']}")
    returned = response.get("model", "")
    if returned != model and not re.fullmatch(re.escape(model) + r"-\d{4}-\d{2}-\d{2}", returned):
        raise ValueError(f"Returned model does not match requested model: {returned}")
    text = extract_text(response)
    (attempt / "output.txt").write_text(text)
    schema = read_json(batch / "judge.schema.json")
    parsed, correction = parse_assessment_json(text, packet, schema)
    if correction:
        save_json(attempt / 'syntax_normalization.json', correction)
    obj, removed = normalize_assessment_envelope(parsed, packet, schema)
    if removed:
        save_json(attempt / "envelope_normalization.json", {"removed_exact_echoes": removed,
                   "policy": "Exact schema metadata and matching item_id only; scientific fields unchanged"})
    validate_assessment(obj, packet, schema)
    obj = derive_assessment_scores(obj, schema)
    result = {
        "idea_id": packet["item_id"], "input_sha256": mapping["input_sha256"],
        "rubric_id": read_json(batch / "manifest.json")["rubric_id"],
        "rubric_sha256": sha((batch / "rubric.json").read_bytes()),
        "pass_id": f"{batch.name}:{model}", "evaluated_at": now(),
        "evaluator": {"type": "llm", "identifier": returned,
                      "configuration": json.dumps({"requested_model": model, "reasoning": config["reasoning_effort"],
                          "tools": [], "prompt_sha256": sha((batch / "system_prompt.md").read_bytes())})},
        **obj,
    }
    from jsonschema import Draft7Validator, FormatChecker
    Draft7Validator(read_json(batch / "score.schema.json"), format_checker=FormatChecker()).validate(result)
    save_json(attempt / "assessment.json", result)
    record["status"] = "valid"
    record["finished_at"] = now()
    save_json(attempt / "record.json", record)
    save_json(attempt.parent / "accepted.json", {"attempt": attempt.name, "assessment_sha256": sha(canonical(result))})
    return result


def evaluate_item(batch, model, packet, mapping, config, base, key, transport="http"):
    item_dir = batch / "runs" / model / packet["item_id"]
    item_dir.mkdir(parents=True, exist_ok=True)
    accepted = item_dir / "accepted.json"
    if accepted.exists():
        pointer = read_json(accepted)
        result = read_json(item_dir / pointer["attempt"] / "assessment.json")
        if sha(canonical(result)) != pointer["assessment_sha256"]:
            raise ValueError("Accepted result has changed")
        return True
    attempts = sorted(item_dir.glob("attempt-*"))
    # Recover a completed API response after local interruption without spending again.
    for attempt in attempts:
        record = read_json(attempt / "record.json")
        if record["status"] == "started":
            if not (attempt / "response.json").exists():
                raise RuntimeError(f"Indeterminate prior attempt at {attempt}; reconcile before retrying")
            try:
                finalize(attempt, read_json(attempt / "response.json"), packet, mapping, batch, model, config, record)
                return True
            except Exception as exc:
                record.update(status="invalid", error=str(exc)[:1500], finished_at=now())
                save_json(attempt / "record.json", record)
    for number in range(len(attempts) + 1, config["max_attempts"] + 1):
        attempt = item_dir / f"attempt-{number:02d}"
        attempt.mkdir()
        payload = request_payload(model, (batch / "system_prompt.md").read_text(), packet, config)
        save_json(attempt / "request.json", payload)
        record = {"status": "started", "requested_model": model, "item_id": packet["item_id"], "transport": transport,
                  "started_at": now(), "endpoint": base, "usage": None,
                  "request_sha256": sha(canonical(payload)),
                  "cost": {"estimated_usd": None, "actual_billed_usd": None}}
        save_json(attempt / "record.json", record)
        start = time.monotonic()
        try:
            if transport == "codex-cli":
                response = call_codex(model, (batch / "system_prompt.md").read_text(), packet, attempt, config)
            else:
                response = call_response(base, key, payload, attempt, config["timeout_seconds"])
            record["latency_seconds"] = round(time.monotonic() - start, 3)
            finalize(attempt, response, packet, mapping, batch, model, config, record)
            print(f"{model} {packet['item_id']} valid; usage={record['usage']}; USD_est={record['cost']['estimated_usd']}", flush=True)
            return True
        except Exception as exc:
            record.update(status="invalid" if (attempt / "response.json").exists() else "transport_error",
                          error=(str(exc).replace(key, "[REDACTED]") if key else str(exc))[:1500], finished_at=now(),
                          latency_seconds=round(time.monotonic()-start, 3))
            save_json(attempt / "record.json", record)
            print(f"{model} {packet['item_id']} {record['status']}: {record['error'][:240]}", flush=True)
            # No invisible retries on failed network calls or unsupported API options.
            if record["status"] == "transport_error":
                return False
    return False


def run(batch, models=None, use_codex_auth=False, limit=None):
    batch = Path(batch).resolve()
    verify_batch(batch)
    config = read_json(batch / "config.json")
    selected = models or config["models"]
    if any(m not in config["models"] for m in selected):
        raise ValueError("Requested model was not frozen in batch config")
    if use_codex_auth:
        base, key, transport = "codex-cli", None, "codex-cli"
    else:
        base, key = credentials(False)
        transport = "http"
    packets = read_json(batch / "packets.json")
    if limit:
        packets = packets[:limit]
    mapping = {m["item_id"]: m for m in read_json(batch / "mapping.json")}
    with (batch / ".run.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for model in selected:  # Astra completes before other models start.
            print(f"START {model}: {len(packets)} ideas", flush=True)
            # Complete the first outstanding review before fan-out. An unavailable
            # gateway must not consume an attempt for every remaining idea.
            first = next((p for p in packets if not
                          (batch / "runs" / model / p["item_id"] / "accepted.json").exists()), None)
            if first is not None:
                if not evaluate_item(batch, model, first, mapping[first["item_id"]], config, base, key, transport):
                    raise RuntimeError(f"{model} first outstanding review failed; no further requests launched")
            with concurrent.futures.ThreadPoolExecutor(max_workers=config["concurrency"]) as pool:
                futures = [pool.submit(evaluate_item, batch, model, p, mapping[p["item_id"]], config, base, key, transport)
                           for p in packets]
                valid = sum(f.result() for f in concurrent.futures.as_completed(futures))
            print(f"DONE {model}: {valid}/{len(packets)}", flush=True)
            if valid != len(packets):
                raise RuntimeError(f"{model} incomplete; inspect attempts before next model")
