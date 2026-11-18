"""Version-bound first matched graph slot; original native workflow unchanged."""
from pathlib import Path
import argparse
import contextlib
import hashlib
import json
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
P = ROOT.parents[2]
from binding import select,validate_output,read as bound_read,verify_bindings
sys.path.insert(0, str(P / 'adapters'))
import sciagents_matched_graph as matched
import sciagents as original
from common import read, save, now, safe, InfrastructureFailure, NativeFailure
from offline_support import require_offline

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class FixtureBoundary(BaseException): pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--domain-json', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--fixture', action='store_true')
    args = parser.parse_args()
    domain_id,manifest_path,manifest,passthrough=select(args.domain_json)
    assert passthrough is None, 'Accepted old domain must use its unchanged original driver'
    validate_output(args.output_dir,manifest,args.fixture)
    PACKAGE=manifest_path.parent
    output = require_offline(args.output_dir, fresh_markers=('native_chat_history.json', 'native_partial_chat_history.json', 'result.json'))
    assert str(args.domain_json.resolve()) == manifest['domain_json']
    assert sha(args.domain_json) == manifest['domain_sha256']
    assert args.fixture or str(output) == manifest['first_slot_output']
    for path, digest in manifest['bindings'].items(): assert sha(path) == digest, path
    graph_bundle = Path(manifest['graph_bundle'])
    material = {k: manifest[k] for k in ('method', 'domain', 'comparison_scope', 'data_version', 'corpus_id', 'corpus_sha256', 'graph_input_version', 'graph_sha256', 'embedding_sha256')}
    material.update(manifest_path=str(PACKAGE / 'manifest.json'), manifest_sha256=sha(PACKAGE / 'manifest.json'),
        original_graph_transfer_included=False, native_context_fresh=True,slot=output.name,fixture=args.fixture)
    save(output / 'input_material_version.json', material)
    original_setup = matched.setup
    original_completion = original.AstraClient.completion
    observed = {}
    first_calls = []
    def audited_setup(out, bundle, allow_pilot=False):
        native = original_setup(out, bundle, allow_pilot)
        group = native['groupchat']
        checks = {'native13_agents': len(group.agents) == 13,
            'native_auto_speaker': group.speaker_selection_method == 'auto', 'native50_round_limit': group.max_round == 50,
            'fresh_native_group_history': not group.messages, 'unattended_native_user': native['user'].human_input_mode == 'NEVER',
            'correct_matched_graph_nodes': len(native['G']) == manifest['retained_nodes'], 'correct_matched_graph_edges': native['G'].number_of_edges() == manifest['retained_edges'],
            'all_graph_nodes_have_pinned_bge_vectors': set(native['G']) == set(native['node_embeddings']),
            'model_cache_disabled': all(native[name]['cache_seed'] is None for name in ('gpt4o_config', 'gpt4o_config_graph', 'gpt4turbo_config', 'gpt4turbo_config_graph'))}
        assert all(checks.values())
        observed.update(checks=checks, agents=[x.name for x in group.agents],domain=domain_id,graph_nodes=len(native['G']),graph_edges=native['G'].number_of_edges(),graph_sha256=manifest['graph_sha256'])
        save(output / 'native_structure_acceptance.json', {'at': now(), 'passed': True, **observed,
            'source_sha256': sha(P / 'adapters/sciagents.py'), 'matched_adapter_sha256': sha(P / 'adapters/sciagents_matched_graph.py')})
        return native
    def stop_at_transport(self, messages, system=None, max_tokens=32768, request_id=None, **kwargs):
        first_calls.append({'messages': messages, 'system': system, 'max_tokens': max_tokens, 'request_id': request_id,
            **{k: kwargs[k] for k in ('tools', 'tool_choice', 'response_format') if kwargs.get(k) is not None}})
        save(output / 'first_native_request_fixture.json', first_calls[-1])
        raise FixtureBoundary()
    matched.setup = audited_setup
    fixture_reached = False
    try:
        if args.fixture:
            tool_output = output / 'native_tools_fixture'
            tool_output.mkdir()
            with (output / 'native_tools_fixture.log').open('w') as log, contextlib.redirect_stdout(log):
                tools_acceptance = matched.verify(tool_output, graph_bundle, False)
            assert tools_acceptance['passed'] and tools_acceptance['model_calls'] == 0
            original.AstraClient.completion = stop_at_transport
        result = matched.generate(read(args.domain_json), output, graph_bundle)
    except FixtureBoundary:
        fixture_reached = True
        result = None
    except InfrastructureFailure as exc:
        result = {'status': 'infrastructure_failure', 'proposal_markdown': None, 'native_output_paths': [], 'terminal_reason': safe(exc)}
    except NativeFailure as exc:
        result = {'status': 'native_failure', 'proposal_markdown': None, 'native_output_paths': [], 'terminal_reason': safe(exc)}
    except Exception as exc:
        result = {'status': 'adapter_failure', 'proposal_markdown': None, 'native_output_paths': [], 'terminal_reason': safe(exc), 'error_type': type(exc).__name__}
    finally:
        original.AstraClient.completion = original_completion
        matched.setup = original_setup
    if args.fixture:
        prompt = json.dumps(first_calls, ensure_ascii=False)
        checks = {**observed.get('checks', {}), 'actual_native_graph_and_local_literature_tools': tools_acceptance['passed'],
            'full_generate_reached_first_native_model_boundary': fixture_reached and len(first_calls) == 1,
            'native_first_request_budget_32768': len(first_calls) == 1 and first_calls[0]['max_tokens'] == 32768,
            'domain_prompt_present': any(read(args.domain_json)['prompt'].replace('提出 5 条', '提出 1 条', 1) in (message.get('content') or '') for call in first_calls for message in call['messages']),
            'matched_abstract_graph_disclosed_to_native_agents': 'Full text was not used to build this graph.' in prompt,
            'no_original_biograph_runtime_access': not (P / 'inputs/sciagents_graph').exists(),
            'own_domain_graph_and_material_bound': observed.get('domain')==domain_id and sha(Path(manifest['graph_bundle'])/'large_graph_simple_giant.graphml')==manifest['graph_sha256'],
            'native_graph_counts_match_domain_receipt': observed.get('graph_nodes')==manifest['retained_nodes'] and observed.get('graph_edges')==manifest['retained_edges'],
            'zero_model_api_attempts': not (output / 'api_events.jsonl').exists() and not list((output / 'api_requests').glob('*/request.json')),
            'no_proposal_or_native_final_output': not (output / 'proposal.md').exists() and not (output / 'native_chat_history.json').exists()}
        save(output / 'fixture_acceptance.json', {'at': now(), 'passed': all(checks.values()), 'checks': checks,
            'model_calls': 0, 'comparison_scope': manifest['comparison_scope'], 'result_error': result,
            'fixture_is_not_a_generated_proposal': True})
        return 0 if all(checks.values()) else 2
    result.update(material, graph_bundle=str(graph_bundle), matched_domain_terminal_acceptance_required_for_more_slots=True)
    save(output / 'result.json', result)
    return 0

if __name__ == '__main__': raise SystemExit(main())
