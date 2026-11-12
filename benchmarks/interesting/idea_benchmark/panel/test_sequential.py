"""Offline behavioral tests; never calls a provider."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from . import sequential as S

QUOTE = '这是可核验的足够长的原始证据内容'


def assessment(ident, score=70):
    return {'card_id': ident, 'dimensions': {d: {'score': score, 'reason': '具体依据'}
            for d in list('NPISFEC')+['interesting']}, 'evidence_quote': QUOTE,
            'critical_issue': '无', 'uncertainty': '未验证', 'revision_from_notes': '无'}


def result(stage):
    return {'notes': [{'card_id': i, 'mechanism': '机制', 'strength': '优势', 'limitation': '局限',
                       'evidence_quote': QUOTE} for i in stage['card_ids']],
            'calibration_note': '依据机制完整性与明确边界评价，不强制排名',
            'assessments': [] if stage['kind']=='read' else [assessment(i) for i in stage['card_ids']],
            'revisions': []}


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.cards = {f'card_{i:02d}': {'card_id': f'card_{i:02d}', 'idea_text': 'L1: '+QUOTE} for i in range(1,17)}
        self.stages = S.stages(list(self.cards))

    def test_warmup_then_tail_then_backfill_exactly_once(self):
        self.assertEqual([s['kind'] for s in self.stages], ['read','read','score','score','backfill','backfill'])
        self.assertEqual(len(self.stages[3]['card_ids']),1)
        state=S.initial_state()
        for stage in self.stages:
            payload=S.payload_for(stage,self.cards,state)
            visible={c['card_id'] for c in payload['current_cards']+payload['previous_card_originals']}
            self.assertEqual(visible,set(state['seen']+stage['card_ids']))
            obj=S.validate_result(result(stage),stage,self.cards,state)
            state=S.advance(state,obj,stage)
        self.assertEqual(set(state['ledger']),set(self.cards))
        self.assertEqual(len(state['history']),16)
        self.assertEqual(state['history'][0]['card_id'],'card_11')
        self.assertEqual(state['history'][-1]['card_id'],'card_10')

    def ready(self):
        state=S.initial_state()
        for stage in self.stages[:3]:state=S.advance(state,result(stage),stage)
        return state,self.stages[3]

    def test_revision_one_old_card_with_provenance(self):
        state,stage=self.ready();obj=result(stage)
        rev={'card_id':'card_11','reason':'旧可行性估计过高，重新审视依赖',
             'trigger_card_ids':['card_16'],'assessment':assessment('card_11',65)}
        obj['revisions']=[rev]
        S.validate_result(obj,stage,self.cards,state)
        updated=S.advance(state,obj,stage)
        self.assertEqual(updated['history'][-1]['old']['dimensions']['N']['score'],70)
        self.assertEqual(updated['ledger']['card_11']['dimensions']['N']['score'],65)
        self.assertEqual(state['ledger']['card_11']['dimensions']['N']['score'],70)
        for bad in [dict(obj,revisions=[rev,rev]),dict(obj,revisions=[dict(rev,card_id='card_01')]),
                    dict(obj,revisions=[dict(rev,card_id='card_16')]),
                    dict(obj,revisions=[dict(rev,trigger_card_ids=['card_01'])]),
                    dict(obj,revisions=[dict(rev,assessment=assessment('card_11'))])]:
            with self.assertRaises((ValueError,AssertionError)):S.validate_result(bad,stage,self.cards,state)

    def test_warmup_forbids_scores_and_foreign_evidence(self):
        stage=self.stages[0];obj=result(stage)
        obj['assessments']=[assessment('card_01')]
        with self.assertRaises(ValueError):S.validate_result(obj,stage,self.cards,S.initial_state())
        obj=result(stage);obj['notes'][0]['score']=70
        with self.assertRaises(ValueError):S.validate_result(obj,stage,self.cards,S.initial_state())
        obj=result(stage);obj['notes'][0]['evidence_quote']='其他卡片的证据不能借用'
        with self.assertRaises(ValueError):S.validate_result(obj,stage,self.cards,S.initial_state())

    def fixture(self,out):
        S.write(out/'cards.json',list(self.cards.values()))
        S.write(out/'stages.json',self.stages)
        S.write(out/'config.json',{'models':S.MODELS,'effort':'high','read_seconds':2700,'score_seconds':5400})
        (out/'prompt.txt').write_text('offline fixture')

    def test_independent_lanes_and_resume_without_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);self.fixture(out);calls=[]
            def fake(j,p,payload,a,cfg,seconds):
                calls.append(j)
                self.assertNotIn('other_judge',payload)
                return json.dumps(result(payload['stage']),ensure_ascii=False),{}
            a=S.lane(out,'astra',caller=fake)
            b=S.lane(out,'opus',caller=fake)
            self.assertEqual(len(calls),12)
            self.assertEqual(a,b)
            def forbidden(*args):raise AssertionError('Resumed accepted stage called provider')
            self.assertEqual(S.lane(out,'astra',caller=forbidden),a)
            accepted=out/'runs/astra/01-read/accepted.json'
            data=S.read(accepted);data['input_sha256']='wrong';S.write(accepted,data)
            with self.assertRaises(ValueError):S.lane(out,'astra',caller=forbidden)

    def test_failure_does_not_advance_and_needs_explicit_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);self.fixture(out)
            def fail(*args):raise RuntimeError('offline transport failure')
            with self.assertRaises(RuntimeError):S.lane(out,'astra',caller=fail)
            self.assertFalse((out/'runs/astra/state.json').exists())
            def fake(j,p,payload,a,cfg,seconds):return json.dumps(result(payload['stage']),ensure_ascii=False),{}
            with self.assertRaises(RuntimeError):S.lane(out,'astra',caller=fake)
            state=S.lane(out,'astra',retry_failed=True,caller=fake)
            self.assertEqual(len(state['ledger']),16)
            self.assertEqual(len(list((out/'runs/astra/01-read').glob('attempt-*'))),2)


if __name__=='__main__':unittest.main()
