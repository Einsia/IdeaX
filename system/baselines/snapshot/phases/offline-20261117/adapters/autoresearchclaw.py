"""Run frozen AutoResearchClaw native proposal pipeline, stages 1 through 9.

Only integration changes: Astra/xhigh request transport, no model fallback,
isolated output roots, and stop before code generation/experiments.
"""
from __future__ import annotations
import argparse
import dataclasses
import io
import json
import logging
import os
from pathlib import Path
import sys
import threading
import urllib.error
import urllib.request
import uuid
from common import admission, credentials
from offline_support import require_offline, environment_text
from arc_offline_literature import local_backends

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/autoresearchclaw"
COMMIT = "be4ba4755bf1b52220f25e13b2293b5956590070"
sys.path.insert(0, str(SOURCE))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def retrieval_summary(native_out, retrieval_errors):
    candidates_path = native_out / 'stage-04/candidates.jsonl'
    rows = [json.loads(line) for line in candidates_path.read_text().splitlines() if line.strip()] if candidates_path.exists() else []
    web_path = native_out / 'stage-04/web_search_result.json'
    web = json.loads(web_path.read_text()) if web_path.exists() else {}
    meta_path = native_out / 'stage-04/search_meta.json'
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    # URLs/source labels in native model fallback rows are not live retrieval.
    real = sum(row.get('source') != 'seminal_library' and not row.get('is_placeholder') for row in rows) if meta.get('real_search') else 0
    web_count = sum(web.get(key, 0) for key in ('web_results_count', 'scholar_papers_count', 'crawled_pages_count'))
    return {'real_candidate_papers': real, 'web_scholar_crawl_results': web_count,
            'native_real_search': bool(meta.get('real_search')),
            'native_seminal_papers': sum(row.get('source') == 'seminal_library' for row in rows),
            'transport_error_count': len(retrieval_errors), 'retrieval_degraded': bool(retrieval_errors)}


def retrieval_unavailable(summary):
    return summary['retrieval_degraded'] and summary['real_candidate_papers'] == 0 and summary['web_scholar_crawl_results'] == 0


def stage4_outage_guard(execute_stage, cancel_event, out, retrieval_errors):
    """Run native Stage4 fully, then use the runner's own between-stage stop."""
    def guarded(stage, *args, **kwargs):
        result = execute_stage(stage, *args, **kwargs)
        if int(stage) == 4 and getattr(result.status, 'value', result.status) == 'done':
            summary = retrieval_summary(out / 'native', retrieval_errors)
            if retrieval_unavailable(summary):
                write_json(out / 'stage4_infrastructure_boundary.json', {
                    'reason': 'All real literature services unavailable after complete native Stage4; infrastructure stop before Stage5.',
                    'native_stage4_result': dataclasses.asdict(result),
                    'native_retrieval': summary, 'resume_from_stage': 4,
                    'native_fallback_outputs_preserved': True,
                    'native_stage_result_unchanged': True,
                    'runner_cancel_event_is_infrastructure_guard_not_user_cancel': True,
                })
                cancel_event.set()
        return result
    return guarded


def completed_native_request_cache(out):
    """Index prior successful wire payloads for exact same-stage recovery only."""
    cache = {}
    for path in sorted((out / 'api_requests').glob('*/request.json')):
        receipt = path.parent / 'receipt.json'
        if not receipt.exists() or not (path.parent / 'response.json').exists():
            continue
        if json.loads(receipt.read_text()).get('status') != 'completed':
            continue
        payload = json.loads(path.read_text())
        cache.setdefault(json.dumps(payload, ensure_ascii=False, sort_keys=True), []).append(path.parent.name)
    return cache


def native_hypothesis_artifacts(out):
    stage = out / 'native/stage-08'
    paths = [stage / 'hypotheses.md', *stage.glob('perspectives/**/*')]
    return [path for path in paths if path.is_file() and path.stat().st_size > 0]


def run(domain, out, dry_run=False, resume_from_stage=None, transport_recovery=None):
    if resume_from_stage is not None or transport_recovery is not None:
        raise ValueError('Offline protocol requires a fresh native context; online recovery is disabled')
    require_offline(out,fresh_markers=('native','api_requests','result.json','config.json'))
    from researchclaw.config import (RCConfig, ProjectConfig, ResearchConfig,
        RuntimeConfig, NotificationsConfig, KnowledgeBaseConfig,
        OpenClawBridgeConfig, LlmConfig, ExperimentConfig)
    from researchclaw.adapters import AdapterBundle
    from researchclaw.pipeline.runner import execute_pipeline
    from researchclaw.pipeline import runner as native_runner
    from researchclaw.pipeline.stages import Stage, StageStatus
    from researchclaw.llm import client as native_client

    out.mkdir(parents=True, exist_ok=True)
    if resume_from_stage is not None:
        if transport_recovery is not None:
            transport_recovery.validate(out, resume_from_stage)
        elif resume_from_stage != 4:
            raise ValueError('Only audited same-run literature-stage recovery is supported')
        prior = json.loads((out / 'result.json').read_text())
        if prior.get('status') != 'infrastructure_failure' or (transport_recovery is None and native_hypothesis_artifacts(out)):
            raise ValueError('Recovery requires a retrieval infrastructure failure before hypothesis generation')
        for name in ['stage-01/goal.md', 'stage-02/problem_tree.md', 'stage-03/search_plan.yaml']:
            if not (out / 'native' / name).exists():
                raise ValueError('Missing preserved native planning artifact: ' + name)
    topic = domain["prompt"].replace("提出 5 条", "提出 1 条")
    config = RCConfig(
        project=ProjectConfig(name="ar-baseline-" + domain["id"], profile="ml_generic"),
        research=ResearchConfig(topic=topic, domains=("machine learning",)),
        runtime=RuntimeConfig(timezone="UTC"),
        notifications=NotificationsConfig(channel="none", on_gate_required=False),
        knowledge_base=KnowledgeBaseConfig(backend="markdown", root=str(out / "knowledge")),
        openclaw_bridge=OpenClawBridgeConfig(),
        llm=LlmConfig(provider="openai", base_url="http://127.0.0.1:8765/v1",
                      api_key_env="OPENAI_API_KEY", primary_model="gpt-6-astra", fallback_models=()),
        # Docker design constraints are native. No container is started: stage 9 is the boundary.
        experiment=ExperimentConfig(mode="docker"),
    )
    cfg = dataclasses.asdict(config)
    cfg["benchmark_boundary"] = {"to_stage": 9, "model": "gpt-6-astra", "reasoning_effort": "xhigh", "commit": COMMIT}
    cfg["benchmark_boundary"]["retrieval_outage_guard"] = 'Complete native Stage4 including fallback, then pause before Stage5 only when all real retrieval is unavailable with transport errors.'
    cfg['offline_protocol']={'corpus':'inputs/corpus/corpus.sqlite','native_queries_and_selection_unchanged':True,'network_backends':'replaced_by_local_raw_search_read','fresh_context':True}
    write_json(out / "config.json", cfg)
    if dry_run:
        return {"status": "preflight_ok", "proposal_markdown": None, "native_output_paths": [], "terminal_reason": None,
                "native_commit": COMMIT, "stage_boundary": 9}
    _, private_key = credentials()
    os.environ["OPENAI_API_KEY"] = private_key

    native_client._NEW_PARAM_MODELS = native_client._NEW_PARAM_MODELS | {"gpt-6"}
    native_client._NO_TEMPERATURE_MODELS = native_client._NO_TEMPERATURE_MODELS | {"gpt-6"}
    from common import AstraClient, InfrastructureFailure, NativeFailure
    transport = AstraClient(out)
    original_raw = native_client.LLMClient._raw_call
    calls = json.loads((out / 'api_calls.json').read_text()) if resume_from_stage else []
    replay_cache = completed_native_request_cache(out) if resume_from_stage and transport_recovery is None else {}
    replay_events = []
    call_lock = threading.Lock()
    def shared_raw(client, model, messages, max_tokens, temperature, json_mode):
        messages=[{'role':'system','content':environment_text(out)},*messages]
        # Native client raises modern reasoning models to 32768; preserve that rule.
        budget = max(max_tokens, 32768)
        payload = {'model': 'gpt-6-astra', 'messages': messages, 'reasoning_effort': 'xhigh',
                   'max_completion_tokens': budget, 'stream': True, 'stream_options': {'include_usage': True}}
        if json_mode:
            payload['response_format'] = {'type': 'json_object'}
        if transport_recovery is not None and not transport_recovery.resolved:
            raw = transport_recovery.completion(payload, transport, calls)
            return client._parse_chat_completions_response(raw, model)
        cached_ids = replay_cache.get(json.dumps(payload, ensure_ascii=False, sort_keys=True), [])
        if cached_ids:
            cached_id = cached_ids.pop(0)
            raw = transport.completion(messages, max_tokens=budget, request_id=cached_id,
                response_format={'type': 'json_object'} if json_mode else None)
            replay_events.append({'request_id': cached_id, 'exact_payload_match': True,
                                  'physical_model_request': False})
            write_json(out / 'native_recovery_replay.json', replay_events)
            return client._parse_chat_completions_response(raw, model)
        with call_lock:
            index = len(calls) + 1
            row = {"index": index, "status": "pending", "native_max_tokens": max_tokens, "effective_max_tokens": budget}
            calls.append(row)
        try:
            raw = transport.completion(messages, max_tokens=budget,
                request_id=f"native-{index:04d}",
                response_format={"type":"json_object"} if json_mode else None)
            row["status"] = "success"
            return client._parse_chat_completions_response(raw, model)
        except Exception as exc:
            row.update(status="failed", error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            write_json(out / "api_calls.json", calls)
    native_client.LLMClient._raw_call = shared_raw
    native_out = out / "native"
    native_out.mkdir(exist_ok=True)
    retrieval_errors = json.loads((out / 'retrieval_transport_errors.json').read_text()) if transport_recovery is not None and (out / 'retrieval_transport_errors.json').exists() else []
    class RetrievalAuditHandler(logging.Handler):
        def emit(self, record):
            if record.name.startswith(('researchclaw.literature.', 'researchclaw.web.')):
                message = record.getMessage()
                if any(token in message.lower() for token in ('429', 'rate-limit', 'timed out', 'timeout', 'circuit breaker')):
                    retrieval_errors.append({'logger': record.name, 'message': message})
                    write_json(out / 'retrieval_transport_errors.json', retrieval_errors)
    audit_handler = RetrievalAuditHandler()
    logging.getLogger().addHandler(audit_handler)
    cancel_event = threading.Event()
    original_execute_stage = native_runner.execute_stage
    native_runner.execute_stage = stage4_outage_guard(original_execute_stage, cancel_event, out, retrieval_errors)
    try:
        with local_backends(out):
            results = execute_pipeline(run_dir=native_out, run_id=out.name,
                config=config, adapters=AdapterBundle.from_config(config),
                from_stage=Stage.TOPIC_INIT,
                to_stage=Stage.EXPERIMENT_DESIGN, auto_approve_gates=True,
                kb_root=out / "knowledge", cancel_event=cancel_event)
    finally:
        native_runner.execute_stage = original_execute_stage
        native_client.LLMClient._raw_call = original_raw
        logging.getLogger().removeHandler(audit_handler)
    stage_rows = [dataclasses.asdict(x) for x in results]
    write_json(out / "native_stages.json", stage_rows)
    hypothesis = native_out / "stage-08/hypotheses.md"
    plan = native_out / "stage-09/exp_plan.yaml"
    from researchclaw.pipeline._helpers import _default_hypotheses
    failures = [x for x in results if x.status == StageStatus.FAILED]
    has_default = hypothesis.exists() and hypothesis.read_text().split("## Generated")[0] == _default_hypotheses(topic).split("## Generated")[0]
    retrieval = retrieval_summary(native_out, retrieval_errors)
    write_json(out / 'native_retrieval_summary.json', retrieval)
    all_retrieval_unavailable = retrieval_unavailable(retrieval)
    if failures or not hypothesis.exists() or not plan.exists() or has_default:
        infrastructure = all_retrieval_unavailable or any(c["status"] == "failed" and c.get("error_type") != "NativeFailure" for c in calls)
        return {"status": "infrastructure_failure" if infrastructure else "native_failure", "proposal_markdown": None,
                "native_output_paths": [str(native_out)], "terminal_reason": "All real native literature retrieval unavailable; downstream pause is an infrastructure failure" if all_retrieval_unavailable else "native stage failure or deterministic fallback hypothesis",
                "native_commit": COMMIT, "stage_results": stage_rows, "fallback_hypothesis": has_default,
                "native_retrieval": retrieval}
    proposal = "# Native hypothesis set\n\n" + hypothesis.read_text() + "\n\n# Native experiment design\n\n```yaml\n" + plan.read_text() + "\n```\n"
    (out / "proposal.md").write_text(proposal, encoding="utf-8")
    if all_retrieval_unavailable:
        return {'status':'infrastructure_failure','proposal_markdown':None,
                'native_output_paths':[str(out / 'proposal.md'),str(hypothesis),str(plan)],
                'terminal_reason':'All real native literature retrieval unavailable; raw output preserved, excluded from main comparison',
                'native_commit':COMMIT,'native_retrieval':retrieval}
    return {"status": "success", "proposal_markdown": str(out / "proposal.md"),
            "native_output_paths": [str(hypothesis), str(plan)], "terminal_reason": None,
            "native_commit": COMMIT, "native_selection": "default 3 perspectives then hypothesis synthesis; one hypothesis-set proposal",
            "native_retrieval": retrieval}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--domain-json", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--resume-from-stage", type=int, choices=[4])
    args=p.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        result=run(json.loads(args.domain_json.read_text()),args.output_dir.resolve(),args.dry_run,args.resume_from_stage)
    except Exception as exc:
        result={"status":"infrastructure_failure","proposal_markdown":None,"native_output_paths":[],"terminal_reason":f"{type(exc).__name__}: {exc}"}
        logging.exception("AutoResearchClaw integration failed")
    write_json(args.output_dir / "result.json", result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in ("success","preflight_ok") else 2

if __name__ == "__main__":
    raise SystemExit(main())
