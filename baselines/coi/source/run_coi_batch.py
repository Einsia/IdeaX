#!/usr/bin/env python3
"""Run frozen CoI tasks with isolated attempts, streaming logs, and resume.

A success requires native nonempty idea and experiment strings. Credentials stay
in child process environments and are omitted from all persisted configuration.
"""
from __future__ import annotations

import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
SECRET_NAME = re.compile(r"(?:KEY|TOKEN|SECRET|PASSWORD|AUTH)", re.IGNORECASE)
REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path, value):
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_result(path):
    if not path.is_file():
        return False, "result.json is missing"
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, "result.json is unreadable or invalid JSON"
    if not isinstance(result, dict):
        return False, "result.json must contain an object"
    for field in ("idea", "experiment"):
        value = result.get(field)
        if not isinstance(value, str) or value.strip().lower() in {"", "none", "null"}:
            return False, f"result.json has no nonempty {field} text"
    return True, "native idea and experiment texts are nonempty"


def prior_run_matches(prior, run_dir, args):
    """Check persisted model settings before reusing a successful run."""
    if prior.get("model") != args.model:
        return False
    try:
        saved_config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError):
        return False
    if not isinstance(saved_config, dict):
        return False
    saved_effort = saved_config.get("COI_REASONING_EFFORT")
    if not isinstance(saved_effort, str) or not saved_effort.strip():
        return False
    if saved_effort != args.reasoning_effort:
        return False
    prior_effort = prior.get("reasoning_effort")
    if prior_effort is not None and prior_effort != saved_effort:
        return False
    saved_model = saved_config.get("MAIN_LLM_MODEL")
    if saved_model not in (None, "") and saved_model != args.model:
        return False
    return True


def task_path(value, tasks_dir):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (tasks_dir / path).resolve()


def effective_config(args):
    if not args.config.is_file():
        raise ValueError(f"configuration is missing: {args.config}")
    source = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    if not isinstance(source, dict):
        raise ValueError("configuration must be a YAML mapping")
    clean, private_env = {}, {}
    for name, value in source.items():
        if not isinstance(name, str) or isinstance(value, (dict, list)):
            raise ValueError("configuration must contain string names and scalar values")
        if value is None:
            continue
        text_value = str(value)
        if text_value.startswith("${") and text_value.endswith("}"):
            text_value = os.environ.get(text_value[2:-1], "")
        if SECRET_NAME.search(name):
            if text_value:
                private_env[name] = os.environ.get(name) or text_value
        else:
            clean[name] = os.environ.get(name, value)
    if args.wire_api == "anthropic":
        settings_path = getattr(args, "claude_settings", None)
        if settings_path:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            provider_env = settings.get("env") or {}
            key = provider_env.get("ANTHROPIC_AUTH_TOKEN") or provider_env.get("ANTHROPIC_API_KEY")
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Claude settings have no nonempty API credential")
            provider_base = provider_env.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
            if args.base_url and args.base_url.rstrip("/").removesuffix("/v1") != provider_base.removesuffix("/v1"):
                raise ValueError("explicit base URL differs from Claude credential provider")
            private_env["ANTHROPIC_AUTH_TOKEN"] = key
            clean["ANTHROPIC_BASE_URL"] = provider_base
        if not any(private_env.get(k) or os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")):
            raise ValueError("Claude API credential is missing; supply --claude-settings or export it")
        native_base = (args.base_url or clean.get("ANTHROPIC_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
        if not native_base.endswith("/v1"):
            native_base += "/v1"
        clean["ANTHROPIC_BASE_URL"] = native_base
        clean["OPENAI_BASE_URL"] = native_base
        clean.setdefault("COI_HTTP_USER_AGENT", "claude-cli/2.1.304 (external, sdk-cli)")
    elif args.auth_file:
        auth = json.loads(args.auth_file.read_text(encoding="utf-8"))
        key = auth.get("OPENAI_API_KEY")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("auth file does not contain a nonempty OPENAI_API_KEY")
        private_env["OPENAI_API_KEY"] = key
    if args.wire_api != "anthropic" and not (private_env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        raise ValueError("OPENAI_API_KEY is missing; supply --auth-file or export it")
    args.reasoning_effort = (args.reasoning_effort or clean.get("COI_REASONING_EFFORT")
                             or os.environ.get("COI_REASONING_EFFORT") or "medium")
    if args.reasoning_effort not in REASONING_EFFORTS:
        raise ValueError("COI reasoning effort is not a supported choice")
    clean.update(is_azure=False, MAIN_LLM_MODEL=args.model, CHEAP_LLM_MODEL=args.model,
                 OPENAI_WIRE_API=args.wire_api, COI_REASONING_EFFORT=args.reasoning_effort)
    if args.base_url and args.wire_api != "anthropic":
        clean["OPENAI_BASE_URL"] = args.base_url
    clean.setdefault("OPENAI_BASE_URL", "https://sbtunnel.xiaoaojianghu.fun/v1")
    for name, value in clean.items():
        if value != "":
            private_env[name] = str(value)
    return clean, private_env


def archive_attempt(run_dir):
    previous = [item for item in run_dir.iterdir() if item.name not in {"attempts", ".llm_cache", ".stage_cache", "saves", "request_attempt_ledger.jsonl", "source_review_feedback.json", "within_run_revision.json", "post_review_source_correction.json"}]
    if not previous:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    archive = run_dir / "attempts" / f"{stamp}-{uuid.uuid4().hex[:8]}"
    archive.mkdir(parents=True)
    for item in previous:
        shutil.move(str(item), str(archive / item.name))


def run_one(task, args, config, extra_env, publish):
    task_id = task["task_id"]
    run_dir = args.output_dir / task_id
    if args.coi_dir.name in {"implementation_v5", "implementation_v6"} and not (run_dir / "source_review_feedback.json").exists() and not (run_dir / "within_run_revision.json").exists():
        import copy
        args = copy.copy(args)
        args.coi_dir = args.coi_dir.parent / "implementation_v4a"
    run_dir.mkdir(parents=True, exist_ok=True)
    result_file = run_dir / "result.json"
    status = dict(task_id=task_id, domain=task.get("domain"), form=task.get("form"), status="pending",
                  model=args.model, reasoning_effort=args.reasoning_effort, wire_api=args.wire_api,
                  output_dir=str(run_dir))
    if args.resume:
        valid, reason = validate_result(result_file)
        prior = {}
        try:
            prior = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        # Adopt an already-running same-task native process when only another
        # run needs a payload repair; never interrupt an in-flight request.
        def native_process_alive(pid):
            try:
                state = Path(f"/proc/{int(pid)}/stat").read_text().split()[2]
                return state not in {"Z", "X"}
            except (OSError, ValueError, IndexError):
                return False
        if (prior.get("status") == "running" and prior.get("pid")
                and prior_run_matches(prior, run_dir, args) and native_process_alive(prior["pid"])):
            status = {**prior, "resumed": True, "adopted_existing_native_process": True}
            publish(status)
            started = datetime.fromisoformat(prior["started_at"]).timestamp()
            while native_process_alive(prior["pid"]):
                if time.time() - started > args.timeout:
                    os.killpg(prior["pid"], signal.SIGTERM)
                    status["timed_out"] = True
                    break
                time.sleep(2)
            valid, reason = validate_result(result_file)
            status.update(status="ok" if valid and not status.get("timed_out") else "failed",
                validation=reason, result=str(result_file) if result_file.exists() else None,
                finished_at=utc_now(), elapsed_seconds=round(time.time() - started, 3),
                returncode=None, exit_evidence="Adopted process exited; successful status requires native result validation")
            atomic_json(run_dir / "status.json", status)
            publish(status)
            return status
        if valid and prior.get("status") == "ok" and prior_run_matches(prior, run_dir, args):
            status = {**prior, "task_id": task_id, "status": "ok", "resumed": True,
                      "model": args.model, "reasoning_effort": args.reasoning_effort,
                      "validation": reason, "result": str(result_file)}
            publish(status)
            return status
        if prior.get("status") == "blocked_gateway_policy" and prior_run_matches(prior, run_dir, args):
            status = {**prior, "model": args.model, "reasoning_effort": args.reasoning_effort, "resumed": True}
            publish(status)
            return status
    archive_attempt(run_dir)
    status.update(started_at=utc_now(), status="running", resumed=False)
    atomic_json(run_dir / "status.json", status)
    publish(status)
    start = time.monotonic()
    try:
        main_py = args.coi_dir / "main.py"
        if not main_py.is_file():
            status.update(status="blocked_checkout", reason=f"missing {main_py}")
            return status
        prompt_path = task_path(task["coi_prompt"], args.tasks_dir)
        prompt = prompt_path.read_text(encoding="utf-8")
        if not prompt.strip():
            status.update(status="blocked_input", reason="task prompt is empty")
            return status
        if task.get("prompt_sha256") and hashlib.sha256(prompt_path.read_bytes()).hexdigest() != task["prompt_sha256"]:
            status.update(status="blocked_input", reason="frozen prompt SHA256 mismatch")
            return status
        if task.get("form") == "insight_lib":
            # CoI reuses topic in relevance/search stages without reattaching
            # the anchor packet. Keep the domain available in every stage.
            prompt = f"研究领域：{task['domain']}（{task.get('domain_id', task['task_id'])}）。\n\n" + prompt
        effective_topic_path = run_dir / "effective_topic.txt"
        effective_topic_path.write_text(prompt, encoding="utf-8")
        (run_dir / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        env = os.environ.copy()
        env.update(extra_env)
        env.update(PYTHONNOUSERSITE="1", PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
        env["PYTHONPATH"] = str(args.coi_dir) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        cmd = [args.python, str(main_py), "--save_file", str(run_dir / "saves"),
               "--improve_cnt", str(args.improve_count), "--min_chain_length", str(args.min_chain_length),
               "--max_chain_length", str(args.max_chain_length), "--max_chain_numbers", str(args.max_chain_numbers)]
        if len(prompt) > 60000:
            cmd.extend(["--topic_file", str(effective_topic_path)])
        else:
            cmd.extend(["--topic", prompt])
        if task.get("anchor_text"):
            anchor = task_path(task["anchor_text"], args.tasks_dir)
            if not anchor.is_file():
                status.update(status="blocked_input", reason=f"missing anchor file: {anchor}")
                return status
            if task.get("seed_sha256") and hashlib.sha256(anchor.read_bytes()).hexdigest() != task["seed_sha256"]:
                status.update(status="blocked_input", reason="frozen anchor SHA256 mismatch")
                return status
            cmd.extend(["--anchor_paper_path", str(anchor)])
        metadata = {name: task.get(name) for name in ("task_id", "domain", "form", "source_input", "source_section", "anchor_text", "seed_sha256", "prompt_sha256")}
        metadata.update(coi_prompt=str(prompt_path), python=args.python, coi_dir=str(args.coi_dir),
                        effective_topic=str(effective_topic_path),
                        effective_topic_sha256=hashlib.sha256(effective_topic_path.read_bytes()).hexdigest(),
                        config_source=str(args.config), model=args.model, reasoning_effort=args.reasoning_effort,
                        wire_api=args.wire_api,
                        base_url=config.get("OPENAI_BASE_URL"), is_azure=False, timeout_seconds=args.timeout,
                        improve_count=args.improve_count, min_chain_length=args.min_chain_length,
                        max_chain_length=args.max_chain_length, max_chain_numbers=args.max_chain_numbers,
                        started_at=status["started_at"])
        metadata["runtime_sha256"] = {name: hashlib.sha256((args.coi_dir / name).read_bytes()).hexdigest()
            for name in ("LLM.py", "LLM_anthropic.py", "main.py", "agents.py", "searcher/sementic_search.py")
            if (args.coi_dir / name).is_file()}
        atomic_json(run_dir / "run_metadata.json", metadata)
        with (run_dir / "stdout.log").open("w", encoding="utf-8") as stdout, (run_dir / "stderr.log").open("w", encoding="utf-8") as stderr:
            process = subprocess.Popen(cmd, cwd=run_dir, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            status["pid"] = process.pid
            atomic_json(run_dir / "status.json", status)
            publish(status)
            try:
                returncode = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                status.update(status="failed", reason="task_timeout", timed_out=True, returncode=process.returncode)
                return status
        valid, validation = validate_result(result_file)
        status.update(status="ok" if returncode == 0 and valid else "failed", returncode=returncode,
                      validation=validation, result=str(result_file) if result_file.is_file() else None)
        if returncode:
            status["reason"] = "CoI child process failed; inspect stderr.log"
            error_text = (run_dir / "stderr.log").read_text(encoding="utf-8", errors="replace")
            if "ModelMismatchError" in error_text or "anthropic_unexpected_model_fallback" in error_text:
                status.update(reason="model_mismatch", failure_category="model_identity")
            elif "GatewayPolicyError" in error_text or ("invalid_prompt" in error_text and "flagged" in error_text):
                status.update(status="blocked_gateway_policy",
                    reason="Model gateway rejected the paper-analysis prompt (invalid_prompt); no idea generated and no alternate-route retry")
            elif ("TransientGatewayError" in error_text or
                  "Model response unsuccessful" in error_text or
                  "response_failed" in error_text):
                status.update(reason="transient_gateway_exhausted", failure_category="gateway_transport")
            elif "RemoteProtocolError" in error_text or "missing_final_sse" in error_text:
                status.update(reason="incomplete_gateway_stream", failure_category="gateway_transport")
        elif not valid:
            status["reason"] = validation
        return status
    except (OSError, ValueError, KeyError) as exc:
        status.update(status="failed", reason=f"runner error ({type(exc).__name__}); inspect runner_error.log")
        safe_message = str(exc)
        for name, value in {**os.environ, **extra_env}.items():
            if SECRET_NAME.search(name) and value and len(value) > 3:
                safe_message = safe_message.replace(value, "[REDACTED]")
        (run_dir / "runner_error.log").write_text(safe_message + "\n", encoding="utf-8")
        return status
    finally:
        status.update(finished_at=utc_now(), elapsed_seconds=round(time.monotonic() - start, 3))
        atomic_json(run_dir / "status.json", status)
        publish(status)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks-dir", type=Path, required=True)
    ap.add_argument("--coi-dir", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--config", type=Path, default=PROJECT_DIR / "config.yaml.example")
    ap.add_argument("--auth-file", type=Path, help="protected JSON containing OPENAI_API_KEY; never copied to output")
    ap.add_argument("--claude-settings", type=Path, help="protected Claude settings JSON; only provider URL/token are read, never copied")
    ap.add_argument("--model", default="gpt-5.6-sol")
    ap.add_argument("--reasoning-effort", default=None, choices=REASONING_EFFORTS,
                    help="Responses reasoning effort; defaults to config/environment, then medium")
    ap.add_argument("--wire-api", default=os.environ.get("OPENAI_WIRE_API", "responses"), choices=["responses", "chat_completions", "anthropic"])
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--limit", type=int, default=0, help="0 means all tasks")
    ap.add_argument("--task-ids", default="", help="comma-separated task IDs for a targeted retry; paths remain relative to tasks-dir")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=1800, help="seconds per task including retrieval")
    ap.add_argument("--resume", action="store_true", help="skip only prior successful tasks with valid native idea and experiment text")
    ap.add_argument("--expected-task-count", type=int, default=0, help="optional assertion on the full input manifest")
    ap.add_argument("--improve-count", type=int, default=1)
    ap.add_argument("--min-chain-length", type=int, default=3)
    ap.add_argument("--max-chain-length", type=int, default=5)
    ap.add_argument("--max-chain-numbers", type=int, default=1)
    ap.add_argument("--include-paper-reference", action="store_true", help="compatibility option; paper_reference inputs are included by default")
    args = ap.parse_args()
    if args.workers < 1 or args.timeout <= 0 or args.limit < 0:
        ap.error("workers and timeout must be positive; limit cannot be negative")
    if not 1 <= args.min_chain_length <= args.max_chain_length or args.max_chain_numbers < 1 or args.improve_count < 0:
        ap.error("invalid CoI chain or improvement parameters")
    for name in ("tasks_dir", "coi_dir", "output_dir", "config"):
        setattr(args, name, getattr(args, name).resolve())
    args.python = str(Path(args.python).resolve()) if Path(args.python).exists() else args.python
    config, extra_env = effective_config(args)
    rows = [json.loads(line) for line in (args.tasks_dir / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row.get("task_id") for row in rows]
    if any(not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", task_id) for task_id in ids) or len(ids) != len(set(ids)):
        raise SystemExit("input task IDs must be unique, nonempty safe directory names")
    source_task_count = len(rows)
    manifest_file = args.tasks_dir / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.is_file() else {}
    expected = args.expected_task_count or manifest.get("task_count")
    if expected and source_task_count != expected:
        raise SystemExit(f"input task count mismatch: expected {expected}, found {source_task_count}")
    if not rows:
        raise SystemExit("input task list is empty")
    if args.task_ids:
        selected = set(args.task_ids.split(","))
        if selected - set(ids):
            raise SystemExit("unknown task IDs: " + ",".join(sorted(selected - set(ids))))
        rows = [row for row in rows if row["task_id"] in selected]
    if args.limit:
        rows = rows[:args.limit]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    statuses = {row["task_id"]: dict(task_id=row["task_id"], form=row.get("form"), status="pending",
                                     model=args.model, reasoning_effort=args.reasoning_effort) for row in rows}
    batch_started = utc_now()

    def publish(status=None):
        with lock:
            if status:
                statuses[status["task_id"]] = dict(status)
            ordered = [statuses[row["task_id"]] for row in rows]
            counts = {name: sum(item["status"] == name for item in ordered) for name in ("ok", "failed", "running", "pending")}
            counts["blocked"] = sum(item["status"].startswith("blocked") for item in ordered)
            summary = dict(total=len(rows), source_task_count=source_task_count, **counts,
                           completed=counts["ok"] + counts["failed"] + counts["blocked"],
                           started_at=batch_started, updated_at=utc_now(), model=args.model,
                           wire_api=args.wire_api, reasoning_effort=args.reasoning_effort,
                           workers=args.workers, timeout_seconds=args.timeout,
                           tasks_dir=str(args.tasks_dir), statuses=ordered)
            atomic_json(args.output_dir / "summary.json", summary)
            if status and status["status"] not in {"running", "pending"}:
                print(json.dumps(dict(task_id=status["task_id"], status=status["status"], **counts, total=len(rows)), ensure_ascii=False), flush=True)

    publish()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, row, args, config, extra_env, publish) for row in rows]
        for future in as_completed(futures):
            future.result()
    final = json.loads((args.output_dir / "summary.json").read_text(encoding="utf-8"))
    print(json.dumps({name: final[name] for name in ("total", "ok", "blocked", "failed")}, ensure_ascii=False, indent=2), flush=True)
    return 0 if final["ok"] == final["total"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
