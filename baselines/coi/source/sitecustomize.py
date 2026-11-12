"""Cap actual model request attempts across same-run recovery; no time cutoff."""
import hashlib, json, os, time
from pathlib import Path

if os.environ.get('COI_ATTEMPT_LEDGER_ENABLED') == '1':
    import LLM
    original_request = LLM.openai_llm._request
    async def bounded_request(self, client, endpoint, payload):
        ledger = Path('request_attempt_ledger.jsonl')
        key = hashlib.sha256(json.dumps({'endpoint': endpoint, 'base_url': self.base_url,
            'payload': payload}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()] if ledger.exists() else []
        prior = sum(row['cache_key'] == key and row['event'] == 'request_started' for row in rows)
        if prior >= 4:
            raise RuntimeError('Logical request attempt budget exhausted for payload ' + key)
        with ledger.open('a') as f:
            f.write(json.dumps({'cache_key': key, 'event': 'request_started', 'time': time.time(),
                               'logical_attempt_number': prior + 1, 'pid': os.getpid()}) + '\n')
        try:
            result = await original_request(self, client, endpoint, payload)
        except Exception as exc:
            with ledger.open('a') as f:
                f.write(json.dumps({'cache_key': key, 'event': 'request_failed', 'time': time.time(),
                                   'error_type': type(exc).__name__}) + '\n')
            raise
        with ledger.open('a') as f:
            f.write(json.dumps({'cache_key': key, 'event': 'request_completed', 'time': time.time(),
                               'response_id': result[1].get('id'), 'usage': result[1].get('usage')}) + '\n')
        return result
    LLM.openai_llm._request = bounded_request

# Shared request admission for the new 38-domain experiment only.
if os.environ.get('BASELINES38_RUNTIME'):
    import sys
    sys.path.insert(0, os.environ['BASELINES38_RUNTIME'])
    from common import async_slot
    import LLM
    _budget_original_request = LLM.openai_llm._request
    async def _budgeted_request(self, client, endpoint, payload):
        async with async_slot(label=os.environ.get('BASELINES38_LABEL', 'coi')):
            return await _budget_original_request(self, client, endpoint, payload)
    LLM.openai_llm._request = _budgeted_request

if os.environ.get('BASELINES38_RUNTIME'):
    from retrieval_recovery import install_coi
    install_coi()
