"""Offline tamper checks; fixtures are not real judge assessments."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import audit_interesting_sequential as A
from . import interesting_sequential as S
from .test_interesting_sequential import result, QUOTE


class AuditTests(unittest.TestCase):
    def test_full_replay_and_reject_changed_native_result(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            cards = [dict(card_id=f'card_{i:02d}', idea_text='L1: '+QUOTE) for i in range(1, 61)]
            S.write(out/'cards.json', cards)
            S.write(out/'stages.json', S.stages([c['card_id'] for c in cards]))
            S.write(out/'config.json', dict(models=S.MODELS, effort='high', read_seconds=2700, score_seconds=5400))
            S.write(out/'mapping.json', [dict(card_id=c['card_id'], task_id=c['card_id'], text_path='fixture') for c in cards])
            (out/'prompt.txt').write_text('fixture')
            def fake(judge, prompt, payload, attempt, cfg, seconds):
                return json.dumps(result(payload['stage']), ensure_ascii=False), {}
            for judge in S.MODELS:
                S.lane(out, judge, caller=fake)
            S.report(out)
            def native(attempt, judge, prompt, payload, cfg):
                return S.strip((attempt/'raw.txt').read_text()), judge + payload['stage']['stage_id']
            # Only native transport and frozen manifests are fixtures here.
            with patch.object(S, 'verify'), patch.object(A, 'native_response', side_effect=native):
                audited = A.audit(out)
                self.assertTrue(audited['complete'])
                self.assertEqual(audited['distinct_native_sessions'], 28)
                self.assertEqual(audited['judges']['astra']['verified_scores'], 60)
                p = out/'runs/astra/03-score/attempt-01/raw.txt'
                obj = S.read(p); obj['assessments'][0]['score'] = 1; S.write(p, obj)
                with self.assertRaisesRegex(ValueError, 'differs from native'):
                    A.audit(out)

    def test_native_astra_trace_and_tool_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory); payload = {'test': True}; prompt = 'fixture'
            full = prompt + '\n\n## Current item (JSON)\n' + json.dumps(payload, ensure_ascii=False)
            text = '{"ok": true}'
            (attempt/'raw.txt').write_text(text); (attempt/'codex_prompt.md').write_text(full)
            S.write(attempt/'codex_command.json', dict(command=['codex','--model','gpt-6-astra','-c','model_reasoning_effort="high"'], prompt_sha256=S.sha(full.encode())))
            events = [{'type':'thread.started','thread_id':'fixture-session'}, {'type':'item.completed','item':{'type':'agent_message','text':text}}, {'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}}]
            S.write(attempt/'response.json', dict(status='completed', id='fixture-session', output=[{'content':[{'text':text}]}], codex_usage=events[-1]['usage']))
            trace = attempt/'codex.stdout.jsonl'
            trace.write_text('\n'.join(map(json.dumps, events)))
            cfg = {'models':S.MODELS,'effort':'high'}
            self.assertEqual(A.native_response(attempt,'astra',prompt,payload,cfg)[0], {'ok':True})
            events.insert(1, {'type':'item.completed','item':{'type':'command_execution'}})
            trace.write_text('\n'.join(map(json.dumps, events)))
            with self.assertRaisesRegex(ValueError, 'used tools'):
                A.native_response(attempt,'astra',prompt,payload,cfg)


if __name__ == '__main__':
    unittest.main()
