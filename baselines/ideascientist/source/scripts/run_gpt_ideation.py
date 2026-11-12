#!/usr/bin/env python3
"""Run the original IdeaScientist agents using GPT Responses and the vault API.

No database download is needed. Credentials stay in memory; run_config.json
records only public connection settings and the selected evidence policy.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests


def _codex_profile(directory: Path) -> tuple[dict, str]:
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError as exc:
            raise ValueError("Python 3.10 requires pip install 'ideascientist[gpt]' for --use-codex-config") from exc
    config = tomllib.loads((directory / "config.toml").read_text())
    provider = config.get("model_providers", {}).get(config.get("model_provider"), {})
    if provider.get("wire_api", "responses") != "responses":
        raise ValueError("The selected Codex provider is not configured for Responses")
    base = provider.get("base_url", "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get(provider.get("env_key", ""), "")
    if not key:
        auth_file = directory / "auth.json"
        auth = json.loads(auth_file.read_text()) if auth_file.exists() else {}
        key = auth.get("OPENAI_API_KEY", "")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("No API key for the selected Codex provider (OAuth-only auth is not supported)")
    return {"model": config.get("model"), "base_url": base}, key.strip()


def configure(args: argparse.Namespace) -> dict:
    base = args.base_url or os.environ.get("IDEASCIENTIST_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    model = args.model or os.environ.get("IDEASCIENTIST_MODEL")
    key = os.environ.get("IDEASCIENTIST_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    credential_source = "environment"
    if args.use_codex_config:
        directory = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        profile, profile_key = _codex_profile(directory)
        if base and base.rstrip("/") != profile["base_url"]:
            raise ValueError("--use-codex-config cannot send its key to a different base URL; use an environment API key instead")
        base = profile["base_url"]
        model = model or profile["model"]
        # A generic ambient OPENAI_API_KEY belongs to its own endpoint, not
        # necessarily this selected provider. Never mix the two profiles.
        key = profile_key
        credential_source = "selected_codex_provider"
    base = (base or "https://api.openai.com/v1").rstrip("/")
    if not model or not model.lower().startswith("gpt-"):
        raise ValueError("Choose a GPT model with --model, IDEASCIENTIST_MODEL, or --use-codex-config")
    if not key or key == "EMPTY":
        raise ValueError("Set OPENAI_API_KEY / IDEASCIENTIST_API_KEY, or use --use-codex-config")
    # All harness imports occur AFTER this configuration; corpus cutoff is
    # frozen at import time by the original evaluation implementation.
    env = {
        "IDEASCIENTIST_MODEL": model,
        "IDEASCIENTIST_BASE_URL": base,
        "IDEASCIENTIST_API_KEY": key,
        "IDEASCIENTIST_WIRE_API": "responses",
        "IDEASCIENTIST_TEXT_TOOLS": "0",
        "IDEASCIENTIST_HISTORY_REASONING": "0",
        "IDEASCIENTIST_VAULT_API_URL": args.vault_api_url.rstrip("/"),
        "IDEASCIENTIST_READER_SOURCE": "structured",
        "IDEASCIENTIST_CUTOFF_DATE": args.cutoff_date,
        "IDEASCIENTIST_REASONING_EFFORT": args.reasoning_effort,
        "IDEASCIENTIST_READER_MAX_TOKENS": str(args.max_output_tokens),
        "IDEASCIENTIST_ROLE_MAX_TOKENS": json.dumps({r: args.max_output_tokens for r in ("gap_finder", "innovator", "reviewer", "report_writer")}),
    }
    # This entry point uses one configured GPT provider for every role.
    for name in ("AGENT_LOOP_BASE_URL", "IDEASCIENTIST_ROLE_BASE_URL", "IDEASCIENTIST_ROLE_MODEL"):
        if os.environ.get(name):
            raise ValueError(f"Unset {name} to avoid silently overriding this GPT profile")
    os.environ.update(env)
    return {
        "model": model, "base_url": base, "wire_api": "responses",
        "credential_source": credential_source, "vault_api_url": env["IDEASCIENTIST_VAULT_API_URL"],
        "reader_source": "structured_results_masked", "full_text_available": False,
        "cutoff_date": args.cutoff_date, "cutoff_policy": "paper year < cutoff year",
        "reasoning_effort": args.reasoning_effort, "max_turns": args.max_turns,
        "max_sub_turns": args.max_sub_turns, "max_output_tokens": args.max_output_tokens,
    }


def write_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_delivery(run_dir: Path, config: dict) -> dict:
    """Verify actual outputs and resolve every numeric report citation."""
    out = run_dir / "outputs"
    required = ("plan.md", "gaps.md", "candidates.md", "scores.md", "report.json")
    missing = [name for name in required if not (out / name).is_file() or (out / name).stat().st_size < 20]
    errors = [f"Missing/empty artifact: {name}" for name in missing]
    report = {}
    if "report.json" not in missing:
        try:
            report = json.loads((out / "report.json").read_text())
        except (ValueError, OSError) as exc:
            errors.append(f"Invalid report JSON: {exc}")
    if not isinstance(report, dict):
        errors.append("Report must be an object")
        report = {}
    for field in ("title", "one_sentence_thesis", "core_problem", "key_novelty", "method", "proposed_evaluation", "falsifiable_predictions", "limitations"):
        if not report.get(field):
            errors.append(f"Report missing {field}")
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
    # Vault IDs are positive. An identifier followed by brackets (e.g.
    # codes[0,0] or tensor[12]) is an array access, not a paper citation.
    citations = sorted({int(n.strip()) for value in strings(report)
                        for group in re.findall(r"(?<!\w)\[([1-9]\d*(?:\s*,\s*[1-9]\d*)*)\]", value)
                        for n in group.split(",")})
    if not citations:
        errors.append("No numeric vault citations in the report")
    bibliography = []
    for pid in citations:
        digest = out / "papers" / f"{pid}.md"
        if not digest.is_file() or digest.stat().st_size < 20:
            errors.append(f"Citation {pid} has no nonempty reader digest")
        response = requests.get(f"{config['vault_api_url']}/api/v1/papers/{pid}", timeout=40)
        if response.status_code == 404:
            errors.append(f"Citation {pid} does not exist in the vault")
            continue
        response.raise_for_status()
        item = response.json()
        if not item.get("date") or item["date"][:4] >= config["cutoff_date"][:4]:
            errors.append(f"Citation {pid} violates the cutoff")
        bibliography.append({k: item.get(k) for k in ("paper_id", "title", "date", "arxiv_id", "url")})
    write_json(out / "bibliography.json", bibliography)
    result = {
        "status": "passed" if not errors else "incomplete", "errors": errors,
        "title": report.get("title"), "citations": citations,
        "reader_digests": len(list((out / "papers").glob("*.md"))),
        "evidence_source": config["reader_source"], "experiments_run": False,
        "scientific_validity_verified": False,
        "report_sha256": hashlib.sha256((out / "report.json").read_bytes()).hexdigest() if (out / "report.json").is_file() else None,
    }
    write_json(run_dir / "delivery.json", result)
    return result


def api_smoke(run_dir: Path, config: dict) -> dict:
    """Two real API calls, including a native tool call and its continuation."""
    from ideascientist.harness.client import AgenticLLMClient
    client = AgenticLLMClient(model=config["model"], base_url=config["base_url"],
                              max_tokens=2048, log_dir=run_dir / "logs", wire_api="responses")
    messages = [{"role": "user", "content": "Call service_probe with value='ready'. After its response, reply with exactly the returned verification_code. Do not guess the code."}]
    tools = [{"type": "function", "function": {"name": "service_probe", "description": "Get the service verification code.", "parameters": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}}}]
    try:
        msg = client.chat(messages, tools=tools, max_retries=1)["choices"][0]["message"]
        calls = msg.get("tool_calls", [])
        if len(calls) != 1 or calls[0]["function"]["name"] != "service_probe":
            raise RuntimeError("GPT did not return the requested native function call")
        if json.loads(calls[0]["function"]["arguments"]).get("value") != "ready":
            raise RuntimeError("Native tool arguments were incorrect")
        messages.extend([msg, {"role": "tool", "tool_call_id": calls[0]["id"], "content": '{"verification_code":"IDEASCIENTIST_GPT_READY_5713"}'}])
        answer = client.chat(messages, tools=[], max_retries=1)["choices"][0]["message"]["content"]
        if "IDEASCIENTIST_GPT_READY_5713" not in answer:
            raise RuntimeError("GPT failed to consume the tool result")
        result = {"status": "passed", "native_tool_call": True, "tool_result_continuation": True, **client.summary()}
        write_json(run_dir / "api_smoke.json", result)
        return result
    finally:
        client.close()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group()
    source.add_argument("--problem")
    source.add_argument("--problem-file", type=Path)
    p.add_argument("--model", default="")
    p.add_argument("--base-url", default="")
    p.add_argument("--use-codex-config", action="store_true", help="Use the selected local Codex provider's model, endpoint and API key")
    p.add_argument("--vault-api-url", default=os.environ.get("IDEASCIENTIST_VAULT_API_URL", "http://127.0.0.1:8901"))
    p.add_argument("--cutoff-date", default="2026-01-01")
    p.add_argument("--reasoning-effort", default="medium", choices=("low", "medium", "high", "xhigh"))
    p.add_argument("--max-turns", type=int, default=40)
    p.add_argument("--max-sub-turns", type=int, default=20)
    p.add_argument("--max-output-tokens", type=int, default=12288)
    p.add_argument("--run-dir", type=Path, default=Path("runs/gpt"))
    p.add_argument("--check", action="store_true", help="Check configuration and vault service without calling GPT")
    p.add_argument("--api-smoke", action="store_true", help="Make two real GPT calls to verify native tools and continuation")
    return p


def main() -> None:
    p = parser()
    args = p.parse_args()
    if min(args.max_turns, args.max_sub_turns, args.max_output_tokens) < 1:
        p.error("Turn and output limits must be positive")
    try:
        datetime.strptime(args.cutoff_date, "%Y-%m-%d")
        config = configure(args)
        response = requests.get(config["vault_api_url"] + "/health", timeout=20)
        response.raise_for_status()
        config["indexed_papers"] = response.json()["indexed_papers"]
    except (ValueError, OSError, requests.RequestException) as exc:
        p.error(str(exc))
    if args.check:
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return
    problem = args.problem_file.read_text(encoding="utf-8") if args.problem_file else args.problem
    if not args.api_smoke and not (problem or "").strip():
        p.error("Provide --problem or --problem-file")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    run_dir = (args.run_dir / (stamp + ("_api_smoke" if args.api_smoke else "_idea"))).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "run_config.json", config)
    print(f"RUN_DIR={run_dir}", flush=True)
    if args.api_smoke:
        result = api_smoke(run_dir, config)
    else:
        from ideascientist.harness import run_ideation
        try:
            summary = asyncio.run(run_ideation(problem, run_dir, model=config["model"], max_turns=args.max_turns, max_sub_turns=args.max_sub_turns))
            write_json(run_dir / "logs" / "summary.json", summary)
            result = validate_delivery(run_dir, config)
        except Exception as exc:
            write_json(run_dir / "delivery.json", {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)})
            raise
    print(json.dumps({"run_dir": str(run_dir), **result}, ensure_ascii=False, indent=2))
    if result["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
