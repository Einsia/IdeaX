"""Frozen public CycleResearcher generation, DeepReviewer, tutorial selection chain."""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

DEPLOYMENT = Path(__file__).resolve().parent
PHASE = DEPLOYMENT.parents[2]
SOURCE = PHASE.parents[1] / 'sources/cycleresearcher'
INPUTS = PHASE / 'inputs/cycleresearcher_domains_n10_standard4_v2'
sys.path.insert(0, str(PHASE / 'adapters'))
sys.path.insert(0, str(SOURCE))
from common import AstraClient, InfrastructureFailure, NativeFailure, now, read, save, safe, event
from offline_support import require_offline
from ai_researcher import CycleResearcher, DeepReviewer
import numpy as np
from format_compatibility import paper_carrier, review_schema, has_native_score, FORMAT_REVISION


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def frozen_json(path, value):
    """Successful artifacts and failed-request payload bindings cannot be replaced."""
    path = Path(path)
    if path.exists():
        if read(path) != value:
            raise ValueError('Frozen artifact differs: ' + str(path))
    else:
        save(path, value)


def frozen_text(path, value):
    path = Path(path)
    data = value.encode('utf-8')
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Frozen carrier differs: ' + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def verify_manifest():
    manifest = read(DEPLOYMENT / 'manifest.json')
    if not manifest:
        raise ValueError('Deployment manifest unavailable')
    for filename, expected in manifest['sha256'].items():
        if sha(filename) != expected:
            raise ValueError('Deployment binding changed: ' + filename)
    return manifest


def tutorial_rating_function():
    """Execute the original function AST, without executing notebook demonstrations."""
    notebook = json.loads((SOURCE / 'Tutorial/tutorial_3.ipynb').read_text())
    tree = ast.parse(''.join(notebook['cells'][13]['source']))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'extract_average_rating')
    scope = {'np': np}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 str(SOURCE / 'Tutorial/tutorial_3.ipynb') + ':cell13', 'exec'), scope)
    return scope['extract_average_rating']


def rating_source(review):
    # Audit annotation only; the score itself always comes from the tutorial AST.
    try:
        float(review.get('meta_review', {})['rating'])
        return 'meta_review'
    except (KeyError, ValueError, TypeError):
        pass
    for item in review.get('reviews', []):
        try:
            float(item['rating'])
            return 'simulated_reviewer_mean'
        except (KeyError, ValueError, TypeError):
            pass
    return 'tutorial_zero_no_parsed_numeric_score'


class MessageTransport:
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        if tokenize or not add_generation_prompt:
            raise ValueError('Unexpected native tokenizer invocation')
        return json.dumps(messages, ensure_ascii=False)


class ModelTransport:
    """One native batch = 10 concurrent logical requests, returned in source order."""
    def __init__(self, output, component, client=None):
        self.output = Path(output) / component
        self.component = component
        self.client = client or AstraClient(self.output)
        self.calls = 0
        self.completed = []

    def generate(self, prompts, sampling_params):
        if self.calls or len(prompts) != 10:
            raise ValueError('Frozen protocol requires exactly one native batch of ten')
        self.calls = len(prompts)
        planned = []
        for index, prompt in enumerate(prompts):
            ident = f'{self.component}-{index + 1:04}'
            item = {'request_id': ident, 'original_index': index,
                    'messages': json.loads(prompt), 'native_max_tokens': sampling_params.max_tokens,
                    'native_temperature': sampling_params.temperature,
                    'native_top_p': sampling_params.top_p,
                    'native_ignore_eos': sampling_params.ignore_eos,
                    'native_stop': sampling_params.stop,
                    'model': 'gpt-6-astra', 'reasoning_effort': 'xhigh',
                    'unsupported_native_sampling': ['temperature', 'top_p', 'ignore_eos']}
            frozen_json(self.output / 'native_calls' / (ident + '.json'), item)
            planned.append(item)
        frozen_json(self.output / 'batch_plan.json', planned)

        def complete(item):
            ident = item['request_id']
            reply = self.client.completion(item['messages'], max_tokens=item['native_max_tokens'],
                request_id=ident, stop=item['native_stop'] or None)
            # The shared client rejects incomplete streams and native length termination.
            # Guard non-stream and injected responses too: partial output is never a score.
            choices = reply.get('choices') or []
            if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
                if choices and choices[0].get('finish_reason') == 'length':
                    raise NativeFailure('Native output budget exhausted')
                # The shared client also accepts JSON replies; a malformed JSON terminal
                # must not remain labelled completed and be replayed forever on resume.
                receipt_path = self.output / 'api_requests' / ident / 'receipt.json'
                receipt = read(receipt_path)
                if receipt and receipt.get('status') == 'completed':
                    archived = self.output / 'transport_validation_failures' / ident / (sha(receipt_path) + '.json')
                    frozen_json(archived, {'original_receipt': receipt, 'original_response': reply,
                        'reason': 'missing_or_nonordinary_terminal_choice'})
                    save(receipt_path, {**receipt, 'status': 'infrastructure_failure',
                        'terminal_validation': 'missing_or_nonordinary_terminal_choice',
                        'preserved_original': str(archived)})
                    event(self.output / 'api_events.jsonl', 'response_validation_failure', request_id=ident,
                          status='infrastructure_failure', usage=reply.get('usage') or None,
                          usage_known=bool(reply.get('usage')))
                raise InfrastructureFailure('Response lacks a complete ordinary terminal choice')
            text = choices[0]['message'].get('content')
            if not isinstance(text, str) or not text.strip():
                raise NativeFailure('Completed native response has empty content')
            frozen_text(self.output / 'raw' / (ident + '.txt'), text)
            frozen_json(self.output / 'completed' / (ident + '.json'), {
                'request_id': ident, 'original_index': item['original_index'],
                'text_sha256': text_sha(text), 'finish_reason': 'stop',
                'response_id': reply.get('id')})
            event(self.output / 'completion_order.jsonl', 'logical_response_completed',
                  request_id=ident, original_index=item['original_index'])
            return SimpleNamespace(outputs=[SimpleNamespace(text=text)])

        results, failures = [None] * 10, []
        # IDs, input order, and payload files exist before any physical submission.
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(complete, item): item for item in planned}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    results[item['original_index']] = future.result()
                    self.completed.append(item['request_id'])
                except Exception as exc:
                    failures.append((item['original_index'], exc))
        self.completed.sort()
        report = {'at': now(), 'completed_request_ids': self.completed,
                  'completed_count': len(self.completed), 'expected_count': 10,
                  'failures': [{'original_index': i, 'type': type(e).__name__, 'error': safe(e)}
                               for i, e in sorted(failures)]}
        save(self.output / 'batch_receipts' / (uuid.uuid4().hex + '.json'), report)
        if failures:
            # Native failure remains terminal even when a sibling also failed in transport.
            native = [e for _, e in failures if isinstance(e, NativeFailure)]
            if native:
                raise NativeFailure('Incomplete native batch: ' + safe(native[0]))
            infrastructure = [e for _, e in failures if isinstance(e, InfrastructureFailure)]
            if infrastructure:
                raise InfrastructureFailure('Incomplete transport batch: ' + safe(infrastructure[0]))
            raise sorted(failures)[0][1]
        if len(self.completed) != 10:
            raise InfrastructureFailure('Native batch completeness gate failed')
        return results


def select(papers, reviews, transports):
    if len(papers) != 10 or len(reviews) != 10 or any(len(t.completed) != 10 for t in transports):
        raise InfrastructureFailure('All ten generation and ten review responses must complete')
    score = tutorial_rating_function()
    ratings = [{'index': i, 'avg_rating': float(score(review)),
                'score_source': rating_source(review), 'decision': review.get('decision', ''),
                'reviewer_count': len(review.get('reviews', []))}
               for i, review in enumerate(reviews)]
    # Original max semantics preserve the first item on equal ratings.
    best = max(ratings, key=lambda x: x['avg_rating'])
    return best, ratings


def run_chain(config, output, clients=None):
    """Invokes the actual official methods and parsers, including in zero-paid fixtures."""
    output = Path(output)
    material = material_record(config)
    frozen_json(output / 'input_material_version.json', material)
    references = Path(config['references_file']).read_bytes().decode('utf-8')
    if text_sha(references) != config['references_sha256']:
        raise ValueError('Frozen reference bytes changed')
    researcher = CycleResearcher.__new__(CycleResearcher)
    researcher.tokenizer = MessageTransport()
    researcher.model = ModelTransport(output, 'researcher', (clients or {}).get('researcher'))
    reviewer = DeepReviewer.__new__(DeepReviewer)
    reviewer.tokenizer = MessageTransport()
    reviewer.model = ModelTransport(output, 'reviewer', (clients or {}).get('reviewer'))
    papers = researcher.generate_paper(topic=config['topic'], references=references, max_tokens=19000, n=10)
    frozen_json(output / 'generated_papers.json', papers)
    carriers, mapping = [], []
    for index, paper in enumerate(papers):
        carrier, compatibility = paper_carrier(paper)
        kind = compatibility['carrier_key']
        carriers.append(carrier)
        frozen_json(output / 'candidates' / f'{index:02}.json', paper)
        frozen_text(output / 'carriers' / f'{index:02}.txt', carrier)
        mapping.append({'original_index': index, 'carrier_key': kind,
                        'carrier_sha256': text_sha(carrier),
                        'generated_text_sha256': text_sha(paper['generated_text']),
                        'native_latex_nonempty': kind == 'latex',
                        'format_compatibility': compatibility})
    frozen_json(output / 'carrier_mapping.json', mapping)
    reviews = reviewer.evaluate(carriers, mode='Standard Mode', reviewer_num=4, max_tokens=35000)
    frozen_json(output / 'native_reviews.json', reviews)
    for index, review in enumerate(reviews):
        frozen_json(output / 'reviews' / f'{index:02}.json', review)
    effective, compatibility = [], []
    tutorial_score = tutorial_rating_function()
    for index, review in enumerate(reviews):
        mapped, evidence = review_schema(review)
        evidence.update(original_index=index, original_tutorial_score=float(tutorial_score(review)),
                        effective_tutorial_score=float(tutorial_score(mapped)))
        effective.append(mapped)
        compatibility.append(evidence)
    frozen_json(output / 'effective_reviews.json', effective)
    frozen_json(output / 'review_format_compatibility.json', compatibility)
    parse_distribution = [{'original_index': i, 'carrier_key': mapping[i]['carrier_key'],
        'official_latex_nonempty': mapping[i]['native_latex_nonempty'],
        'official_reviewers_parsed': len(reviews[i].get('reviews', [])),
        'effective_reviewers_parsed': len(effective[i].get('reviews', [])),
        'original_tutorial_score': compatibility[i]['original_tutorial_score'],
        'effective_tutorial_score': compatibility[i]['effective_tutorial_score'],
        'review_format_mapping': compatibility[i]['mapping'],
        'review_format_error': compatibility[i]['error']} for i in range(10)]
    frozen_json(output / 'parse_distribution.json', parse_distribution)
    if any(not has_native_score(review) or not evidence['compatible']
           for review, evidence in zip(effective, compatibility)):
        raise NativeFailure('Review formatting is missing or ambiguous; tutorial zero retained only as diagnosis')
    best, ratings = select(papers, effective, [researcher.model, reviewer.model])
    selection = {'selected_original_index': best['index'], 'ratings': ratings,
                 'parse_fallback_count': sum(r['score_source'] == 'tutorial_zero_no_parsed_numeric_score' for r in ratings),
                 'original_parser_zero_count': sum(not has_native_score(r) for r in reviews),
                 'review_format_compatibility_count': sum(e['mapping'] != 'official_native_parser' for e in compatibility),
                 'carrier_fallback_count': sum(r['carrier_key'] == 'generated_text' for r in mapping),
                 'tie_break': 'first original index', 'score_scope': 'internal_candidate_selection_only',
                 'completed_logical_responses': {'generation': 10, 'review': 10},
                 'selected_carrier': mapping[best['index']],
                 'selection_source': 'Tutorial/tutorial_3.ipynb cell 13'}
    frozen_json(output / 'selection.json', selection)
    proposal = carriers[best['index']]
    frozen_text(output / 'proposal.md', proposal)
    return {**material, 'status': 'completed', 'proposal_markdown': proposal, 'terminal_reason': None,
            'completed_at': now(), 'native_output_paths': [str(output / name) for name in
                ('generated_papers.json', 'native_reviews.json', 'effective_reviews.json',
                 'review_format_compatibility.json', 'parse_distribution.json', 'carrier_mapping.json',
                 'selection.json', 'proposal.md', 'input_material_version.json')],
            'selected_original_index': best['index'],
            'completed_logical_responses': 20, 'parse_fallback_count': selection['parse_fallback_count'],
            'original_parser_zero_count': selection['original_parser_zero_count'],
            'review_format_compatibility_count': selection['review_format_compatibility_count'],
            'carrier_fallback_count': selection['carrier_fallback_count'],
            'configuration_id': config['configuration_id'], 'is_exact_is_configuration': False,
            'unknown_usage_and_usd': None}


def material_record(config):
    return {'method': 'cycleresearcher', 'domain': config['domain_id'],
            'format_compatibility_revision': FORMAT_REVISION,
        'data_version': config['data_version'], 'corpus_id': config['corpus_id'],
        'corpus_sha256': config['corpus_sha256'],
        'corpus_manifest_sha256': config['corpus_manifest_sha256'],
        'references_sha256': config['references_sha256'],
        'configuration_id': config['configuration_id'],
        'configuration_sha256': sha(INPUTS / config['domain_id'] / 'configuration.json'),
        'deployment_manifest_sha256': sha(DEPLOYMENT / 'manifest.json'),
        'comparison_scope': config['comparison_scope'],
        'raw_corpus_modified': False, 'material_reselection': False}


RUNTIME_FILES = {'run.lock', 'offline_boundary.json', 'offline_launch.json',
                 'local_literature_service.log', 'local_literature_requests.jsonl'}


def checkpoint_files(output):
    return [p for p in output.rglob('*') if p.is_file()
            and p.relative_to(output).parts[0] != 'checkpoints'
            and not (len(p.relative_to(output).parts) == 1 and p.name in RUNTIME_FILES)]


def require_fresh_workspace(output):
    if any(p.name not in RUNTIME_FILES for p in output.iterdir()):
        raise ValueError('Fresh native slot cannot adopt unbound existing artifacts')


def checkpoint(output):
    # Append-only attempt evidence and exact successes are bound before a later explicit retry.
    files = checkpoint_files(output)
    value = {'at': now(), 'output': str(output), 'status': read(output / 'result.json')['status'],
             'run_binding': read(output / 'run_binding.json'),
             'sha256': {str(p.relative_to(output)): sha(p) for p in sorted(files)}}
    target = output / 'checkpoints' / (uuid.uuid4().hex + '.json')
    save(target, value)
    return target


def validate_resume(output, checkpoint_path, binding):
    previous = read(checkpoint_path)
    if (not previous or previous['output'] != str(output)
            or previous['status'] != 'infrastructure_failure' or previous['run_binding'] != binding):
        raise ValueError('Resume requires the same infrastructure-failed run and frozen bindings')
    if (output / 'selection.json').exists() or (output / 'proposal.md').exists():
        raise ValueError('Selected proposals cannot be resumed')
    if {str(p.relative_to(output)) for p in checkpoint_files(output)} != set(previous['sha256']):
        raise ValueError('Checkpoint file set changed')
    for name, expected in previous['sha256'].items():
        path = (output / name).resolve()
        if not path.is_relative_to(output) or sha(path) != expected:
            raise ValueError('Checkpoint artifact changed: ' + name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--domain-json', required=True)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--resume-checkpoint')
    args = ap.parse_args()
    output = require_offline(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'run.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_manifest()
        domain = read(args.domain_json)
        config_file = INPUTS / domain['id'] / 'configuration.json'
        config = read(config_file)
        if sha(args.domain_json) != config['domain_json_sha256']:
            raise ValueError('Domain input differs from the frozen configuration')
        if sha(PHASE / 'inputs/corpus/corpus.sqlite') != config['corpus_sha256']:
            raise ValueError('Frozen raw corpus differs from the selected material version')
        binding = {'output': str(output), 'domain_id': domain['id'],
                   'configuration_sha256': sha(config_file), 'deployment_manifest_sha256': sha(DEPLOYMENT / 'manifest.json')}
        if (output / 'run_binding.json').exists():
            if not args.resume_checkpoint:
                raise ValueError('Existing native slot requires an explicitly audited checkpoint resume')
            validate_resume(output, args.resume_checkpoint, binding)
            frozen_json(output / 'history' / (sha(output / 'result.json') + '.json'), read(output / 'result.json'))
        elif args.resume_checkpoint:
            raise ValueError('No existing native run to resume')
        else:
            require_fresh_workspace(output)
        frozen_json(output / 'run_binding.json', binding)
        material = material_record(config)
        frozen_json(output / 'input_material_version.json', material)
        try:
            result = run_chain(config, output)
        except InfrastructureFailure as exc:
            result = {'status': 'infrastructure_failure', 'terminal_reason': safe(exc), 'proposal_markdown': None,
                      'native_output_paths': [], 'usage': None, 'usd': None}
        except NativeFailure as exc:
            result = {'status': 'native_failure', 'terminal_reason': safe(exc), 'proposal_markdown': None,
                      'native_output_paths': [], 'usage': None, 'usd': None}
        except Exception as exc:
            result = {'status': 'adapter_failure', 'terminal_reason': safe(exc), 'proposal_markdown': None,
                      'native_output_paths': [], 'error_type': type(exc).__name__, 'usage': None, 'usd': None}
        result.update(material)
        save(output / 'result.json', result)
        saved = checkpoint(output) if result['status'] == 'infrastructure_failure' else None
        print(json.dumps({'status': result['status'], 'checkpoint': str(saved) if saved else None}))


if __name__ == '__main__':
    main()
