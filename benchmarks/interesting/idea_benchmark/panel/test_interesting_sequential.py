import json,tempfile,unittest
from pathlib import Path
from . import interesting_sequential as S
QUOTE='这是本卡真实存在的足够长逐字证据'
def assessment(i,score=70):
 return dict(card_id=i,score=score,reason='实质转折理由',departure='不同于常规模板',evidence_quote=QUOTE,uncertainty='待核验近邻',revision_from_notes='无')
def result(stage):
 return dict(notes=[dict(card_id=i,mechanism='机制',strength='优点',limitation='局限',evidence_quote=QUOTE) for i in stage['card_ids']],calibration_note='按构思转折的实质意义判断，不强制分布',assessments=[] if stage['kind']=='read' else [assessment(i) for i in stage['card_ids']],revisions=[])
class Tests(unittest.TestCase):
 def setUp(self):
  self.cards={f'card_{i:02d}':dict(card_id=f'card_{i:02d}',idea_text='L1: '+QUOTE) for i in range(1,61)}
  self.stages=S.stages(list(self.cards))
 def test_all60_once_and_revisions(self):
  state=S.initial_state()
  for n,stage in enumerate(self.stages):
   obj=result(stage)
   if n==3:
    obj['revisions']=[dict(card_id='card_11',reason='旧判断依据不足',trigger_card_ids=stage['card_ids'][:1],assessment=assessment('card_11',65))]
   S.validate_result(obj,stage,self.cards,state);state=S.advance(state,obj,stage)
  self.assertEqual(len(self.stages),14);self.assertEqual(len(state['ledger']),60)
  self.assertEqual(len(state['history']),61);self.assertEqual(state['ledger']['card_11']['score'],65)
  self.assertEqual(state['history'][0]['card_id'],'card_11');self.assertEqual(state['history'][-1]['card_id'],'card_10')
 def test_reject_extra_revision_warmup_score_and_borrowed_quote(self):
  state=S.initial_state();stage=self.stages[0];obj=result(stage);obj['assessments']=[assessment('card_01')]
  with self.assertRaises(ValueError):S.validate_result(obj,stage,self.cards,state)
  for st in self.stages[:3]:state=S.advance(state,result(st),st)
  stage=self.stages[3];obj=result(stage)
  rev=dict(card_id='card_11',reason='依据修正',trigger_card_ids=stage['card_ids'][:1],assessment=assessment('card_11',65))
  obj['revisions']=[rev,rev]
  with self.assertRaises(ValueError):S.validate_result(obj,stage,self.cards,state)
  obj['revisions']=[rev];rev['assessment']['evidence_quote']='不存在的其他卡片引文'
  with self.assertRaises(ValueError):S.validate_result(obj,stage,self.cards,state)
 def test_resume_isolated_no_future_or_model_calls(self):
  with tempfile.TemporaryDirectory() as t:
   out=Path(t);S.write(out/'cards.json',list(self.cards.values()));S.write(out/'stages.json',self.stages)
   S.write(out/'config.json',dict(models=S.MODELS,effort='high',read_seconds=2700,score_seconds=5400));(out/'prompt.txt').write_text('offline')
   calls=[]
   def fake(j,p,payload,a,cfg,seconds):
    calls.append(j);seen=set(payload['own_memory']['seen'])|set(payload['stage']['card_ids'])
    self.assertEqual({c['card_id'] for c in payload['current_cards']+payload['previous_card_originals']},seen)
    return json.dumps(result(payload['stage']),ensure_ascii=False),{}
   a=S.lane(out,'astra',caller=fake);b=S.lane(out,'opus',caller=fake)
   self.assertEqual(len(calls),28);self.assertEqual(a,b)
   def forbidden(*a):raise AssertionError('Unwanted provider call')
   self.assertEqual(S.lane(out,'astra',caller=forbidden),a)
if __name__=='__main__':unittest.main()
