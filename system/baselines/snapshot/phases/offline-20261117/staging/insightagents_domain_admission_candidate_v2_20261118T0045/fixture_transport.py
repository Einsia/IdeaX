"""Deterministic SDK transport fixtures. No sockets or provider calls."""
import collections
import json
import re
import httpx2
from journal_client import JournaledLLMClient


class FixtureTransport(httpx2.BaseTransport):
    def __init__(self, *, converged=False, experts=3, invalid_final=False, incomplete_stage=None,
                 retry_stage=None, crash_after=None):
        self.client = None
        self.calls = []
        self.converged, self.experts, self.invalid_final = converged, experts, invalid_final
        self.incomplete_stage, self.retry_stage, self.crash_after = incomplete_stage, retry_stage, crash_after
        self.counts = collections.Counter()

    def handle_request(self, request):
        original = json.loads((self.client.recorder.logical_dir / 'request.json').read_text())
        args = original['native_arguments']
        stage = args['stage']
        self.calls.append({'stage': stage, 'wire': request.content, 'identity': original['identity']})
        self.counts[stage] += 1
        if self.crash_after is not None and len(self.calls) > self.crash_after:
            raise KeyboardInterrupt('Fixture process interruption')
        if stage == self.retry_stage and self.counts[stage] < 3:
            return httpx2.Response(503, json={'error': {'message': 'fixture retry', 'type': 'server_error'}})
        obj = {'title': 'Fixture proposal', 'method': 'A fixture method'}
        tool_name = args.get('required_tool_name')
        text = None
        if stage == 's2_seed_select': obj = {'pick': 1, 'why': 'Deterministic fixture'}
        elif stage == 's2_rec_filter':
            keep = re.search(r'(?:at most|up to|maximum of|exactly)\s+(\d+)', args['system_prompt'], re.I)
            # Selecting more than keep_n is safe: the untouched native selector
            # applies its own [5,3,2] cap, including shorter candidate lists.
            obj = {'selected': [{'id': i} for i in range(1, 21)]}
        elif stage == 's2_insight':
            obj = {'insights': [{'insight_name': 'Fixture line ' + str(i), 'core_insight': 'Fixture evidence.',
                  'papers': [{'label': 'P1'}, {'label': 'P2'}], 'edges': [],
                  'claims': [{'label': 'P1', 'finding': 'Fixture finding ' + str(j)} for j in range(3)]}
                  for i in range(self.experts)]}
        elif stage == 'stage1_statement.candidate_synthesis':
            obj = {'candidates': [{'problem': 'Fixture question ' + str(i), 'why_significant': 'Fixture reason'} for i in range(3)]}
        elif stage == 'stage1_endorsement.vote':
            obj = {'ranking': [{'candidate': i, 'rank': i, 'reason': 'Fixture reason'} for i in range(1, 4)]}
        elif stage.endswith('.critic'): obj = {'issues': []}
        elif stage == 'stage2_clash.moderator':
            obj = {'summary': {'draft_updates': [], 'open_attacks': [], 'dropped': [], 'settled': [],
                               'converged': self.converged}, 'updated_draft': obj}
        elif stage.endswith('expert_speech') or stage == 'stage1_endorsement.moderator':
            text = 'Fixture statement with no external source claims.'
        if stage == 'stage3.moderator' and self.invalid_final: text = 'not JSON'
        if tool_name:
            output = [{'type': 'function_call', 'id': 'fc_fixture', 'call_id': 'call_fixture',
                       'name': tool_name, 'arguments': json.dumps(obj), 'status': 'completed'}]
        else:
            output = [{'type': 'message', 'id': 'msg_fixture', 'role': 'assistant', 'status': 'completed',
                       'content': [{'type': 'output_text', 'text': text or json.dumps(obj), 'annotations': []}]}]
        incomplete = stage == self.incomplete_stage
        final = {'id': 'resp_fixture', 'object': 'response', 'created_at': 1,
            'model': 'gpt-6-astra', 'status': 'incomplete' if incomplete else 'completed',
            'incomplete_details': {'reason': 'max_output_tokens'} if incomplete else None,
            'output': output, 'usage': {'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12,
               'input_tokens_details': {'cached_tokens': 0}, 'output_tokens_details': {'reasoning_tokens': 1}}}
        kind = 'response.incomplete' if incomplete else 'response.completed'
        event = {'type': kind, 'sequence_number': 1, 'response': final}
        body = ('event: ' + kind + '\ndata: ' + json.dumps(event) + '\n\n').encode()
        return httpx2.Response(200, headers={'content-type': 'text/event-stream'}, content=body)

    def close(self): pass


def make_factory(**options):
    def factory(*args):
        transport = FixtureTransport(**options)
        client = JournaledLLMClient(*args, delegate=transport)
        transport.client = client
        return client
    return factory


client_factory = make_factory()
