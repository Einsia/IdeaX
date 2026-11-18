"""Native LLM API with exact per-call replay and receipts for every SDK attempt."""
import collections
import copy
from dataclasses import asdict
import json
from pathlib import Path
import time

import httpx2
import openai

from evidence import digest, encode, event, freeze, freeze_bytes, sha
from llm_client import LLMClient, LLMResponse, ToolCall


class EvidenceViolation(Exception):
    """Protocol violations must not trigger native JSON fallback handlers."""


class IncompleteOriginalCall(EvidenceViolation):
    """A previously started original call has no durable completed response."""


class FreshStreamPolicy:
    def __init__(self, output, context):
        self.output = Path(output).resolve()
        self.fixture = context['fixture']
        self.contract = {}
    def is_target(self, directory):
        return False
    def is_new_stream(self, directory):
        directory = Path(directory).resolve()
        return (directory.parent == self.output / 'model_calls'
                and (directory / 'request.json').is_file()
                and not (directory / 'native_returned.json').exists())


class PhysicalRecorder(httpx2.BaseTransport):
    def __init__(self, output, delegate=None, scope_context=None):
        self.output = Path(output)
        self.scope_context = scope_context or {}
        self.delegate = delegate or httpx2.HTTPTransport(retries=0, trust_env=False)
        self.logical_dir = None
        self.expected_body = None
        self.physical_index = 0
        self.first_wire_sha = None
        self.max_attempts = 3
        self.policy = FreshStreamPolicy(self.output, self.scope_context)

    def begin(self, logical_dir):
        self.logical_dir = Path(logical_dir)
        self.expected_body = None
        self.physical_index = 0
        self.first_wire_sha = None

    def handle_request(self, request):
        from stream_transport import handle_stream
        return handle_stream(self, request)

    def close(self): self.delegate.close()


class JournaledLLMClient(LLMClient):
    def __init__(self, role, output, binding_sha, progress, verify, delegate=None):
        super().__init__('openai', 'gpt-6-astra', 'offline-model-bridge',
                         max_tokens=2500 if role == 'debate' else 2000,
                         base_url='http://127.0.0.1:8765/v1')
        if self.openai_api_style != 'responses' or self.reasoning_effort != 'xhigh' or self.reasoning_reserve != 2000:
            raise RuntimeError('Native API/model configuration differs from the bound protocol')
        if openai.__version__ != '3.52.0' or self._client.max_retries != 2:
            raise RuntimeError('The reviewed native SDK version or retry default changed')
        self.role, self.output, self.binding_sha = role, Path(output), binding_sha
        self.progress, self.verify = progress, verify
        self.ordinals = collections.Counter()
        binding_path = Path(output) / 'run_binding.json'
        binding = json.loads(binding_path.read_text()) if binding_path.exists() else {}
        self.scope_context = {key: binding.get(key, default) for key, default in {
            'fixture': True, 'run_id': 'fixture:direct-sdk-test', 'admission_id': 'fixture:no-paid-admission',
            'purpose': 'offline-fake-transport', 'comparison_scope': 'offline-fake-transport'}.items()}
        self.recorder = PhysicalRecorder(output, delegate=delegate, scope_context=self.scope_context)
        initial = self._client
        self._client = initial.with_options(http_client=openai.DefaultHttpxClient(
            transport=self.recorder, trust_env=False, follow_redirects=False))
        initial.close()
        original_create = self._client.responses.create
        def recorded_create(**kwargs):
            self.recorder.expected_body = copy.deepcopy(kwargs)
            response = original_create(**kwargs)
            # Preserve the native handling of provider status=incomplete.
            # Transport completeness and native proposal validity are distinct.
            return response
        self._client.responses.create = recorded_create

    def _context(self, stage):
        # The native graph checkpoints only after a seed's whole graph finishes.
        # Distinct structural seed fallbacks must never share a replay ordinal.
        if stage == 's2_rec_filter':
            return {'seed_candidate_index': (self.progress().get('retrieval') or {}).get('next_candidate_idx', 0)}
        return {}

    def complete(self, system_prompt, messages, tools=None, max_tokens=None, required_tool_name=None, *, stage):
        try:
            self.verify()
        except Exception:
            raise EvidenceViolation('Frozen run evidence changed before a native call') from None
        context = self._context(stage)
        group = (self.role, stage, digest(encode(context)))
        self.ordinals[group] += 1
        ordinal = self.ordinals[group]
        identity = {'role': self.role, 'stage': stage, 'context': context, 'ordinal': ordinal}
        ident = digest(encode(identity))
        directory = self.output / 'model_calls' / ident
        request = {'identity': identity, 'run_binding_sha256': self.binding_sha,
                   'model': self.model, 'reasoning_effort': self.reasoning_effort,
                   'api_style': self.openai_api_style, 'reasoning_token_reserve': self.reasoning_reserve,
                   'scope_context': self.scope_context,
                   'native_arguments': {'system_prompt': system_prompt, 'messages': messages,
                                        'tools': tools, 'max_tokens': max_tokens,
                                        'required_tool_name': required_tool_name, 'stage': stage}}
        request_bytes = encode(request)
        if directory.exists():
            if (directory / 'request.json').read_bytes() != request_bytes:
                raise EvidenceViolation('Original native call identity now has a different exact payload')
            receipt_path = directory / 'native_returned.json'
            if not receipt_path.is_file():
                raise IncompleteOriginalCall('Original call has unresolved attempts; coordinator recovery is required')
            receipt = self.validate_cache(directory, request_bytes)
            response_path = directory / 'native_response.json'
            value = json.loads(response_path.read_text())
            for row in receipt['native_usage_rows']:
                self.call_log.append(copy.deepcopy(row) | {'cached_original_response': True})
                self.usage['calls'] += 1
                for name in self.usage:
                    if name != 'calls': self.usage[name] += row.get(name, 0) or 0
            event(self.output / 'logical_calls.jsonl', 'original_native_response_replayed',
                  identity=identity, **self.scope_context, native_response_sha256=receipt['native_response_sha256'],
                  new_physical_attempts=0)
            return LLMResponse(text=value['text'], tool_calls=[ToolCall(**call) for call in value['tool_calls']])
        directory.mkdir(parents=True, exist_ok=False)
        freeze_bytes(directory / 'request.json', request_bytes)
        self.recorder.begin(directory)
        previous = len(self.call_log)
        event(self.output / 'logical_calls.jsonl', 'native_call_started', identity=identity, **self.scope_context,
              request_sha256=digest(request_bytes), run_binding_sha256=self.binding_sha)
        try:
            response = super().complete(system_prompt, messages, tools, max_tokens,
                                        required_tool_name, stage=stage)
            response_path = directory / 'native_response.json'
            freeze(response_path, asdict(response))
            freeze(directory / 'native_returned.json', {
                'identity': identity, 'request_sha256': digest(request_bytes),
                'native_response_sha256': sha(response_path),
                'native_usage_rows': self.call_log[previous:],
                'physical_attempts': self.recorder.physical_index,
                'physical_files': {str(p.relative_to(directory)): sha(p)
                    for p in sorted(directory.glob('physical-*/*')) if p.is_file()},
                'unknown_failed_usage_and_usd_preserved_in_attempt_ledger': True})
            event(self.output / 'logical_calls.jsonl', 'native_call_returned', identity=identity, **self.scope_context,
                  native_response_sha256=sha(response_path), physical_attempts=self.recorder.physical_index)
            return response
        except Exception as exc:
            event(self.output / 'logical_calls.jsonl', 'native_call_failed', identity=identity, **self.scope_context,
                  error_type=type(exc).__name__, physical_attempts=self.recorder.physical_index,
                  usage=None, usd=None, automatic_future_resume=False)
            raise

    @staticmethod
    def validate_cache(directory, request_bytes=None):
        directory = Path(directory)
        request_path = directory / 'request.json'
        receipt = json.loads((directory / 'native_returned.json').read_text())
        request = json.loads(request_path.read_text())
        if (receipt['identity'] != request['identity'] or receipt['request_sha256'] != sha(request_path)
                or (request_bytes is not None and request_path.read_bytes() != request_bytes)
                or receipt['native_response_sha256'] != sha(directory / 'native_response.json')):
            raise EvidenceViolation('Completed native response binding changed')
        files = {str(p.relative_to(directory)): sha(p)
                 for p in sorted(directory.glob('physical-*/*')) if p.is_file()}
        if files != receipt['physical_files'] or not 1 <= receipt['physical_attempts'] <= 3:
            raise EvidenceViolation('Completed physical attempt evidence changed')
        wires = []
        for i in range(1, receipt['physical_attempts'] + 1):
            physical = directory / f'physical-{i:02}'
            wire = sha(physical / 'request_body.json')
            wires.append(wire)
            kind = 'receipt.json' if (physical / 'receipt.json').exists() else 'error.json'
            record = json.loads((physical / kind).read_text())
            if record['request_sha256'] != wire:
                raise EvidenceViolation('Physical request evidence differs')
            if kind == 'receipt.json' and record['response_sha256'] != sha(physical / 'response_body.bin'):
                raise EvidenceViolation('Physical response evidence differs')
        if len(set(wires)) != 1:
            raise EvidenceViolation('SDK retries changed original request bytes')
        last = directory / f"physical-{receipt['physical_attempts']:02}" / 'receipt.json'
        if not last.exists() or json.loads(last.read_text())['http_status'] != 200:
            raise EvidenceViolation('Cache has no original successful HTTP response')
        from stream_transport import validate_stream_directory
        final_dir = directory / f"physical-{receipt['physical_attempts']:02}"
        validate_stream_directory(final_dir, {
            'target_wire_sha256': sha(final_dir / 'native_sdk_request_body.json'),
            'target_stream_wire_sha256': sha(final_dir / 'request_body.json')})
        return receipt

    def snapshot(self):
        return {'ordinals': [[list(key), value] for key, value in self.ordinals.items()],
                'usage': copy.deepcopy(self.usage), 'call_log': copy.deepcopy(self.call_log)}

    def restore(self, value):
        self.ordinals = collections.Counter({tuple(key): count for key, count in value['ordinals']})
        self.usage = copy.deepcopy(value['usage'])
        self.call_log = copy.deepcopy(value['call_log'])

    def close(self): self._client.close()
