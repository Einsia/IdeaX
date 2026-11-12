import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
SCRATCH=ROOT/'.scratch';SCRATCH.mkdir(exist_ok=True)
os.environ.setdefault('IDEAX_SCRATCH',str(SCRATCH))
os.environ.setdefault('TMPDIR',str(SCRATCH))
tempfile.tempdir=str(SCRATCH)

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

class ReleaseTests(unittest.TestCase):
    def command(self,*args,env=None):
        result=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        return result

    def test_source_and_snapshot(self):self.command('scripts/check_release.py')

    def test_native_system_regressions(self):
        env=dict(os.environ,LITGRAPH_API_BASE_URL='https://litgraph.invalid',
                 IDEAX_CURRENT_SYSTEM=str(ROOT/'system/single-full'),
                 IDEAX_CODEX_RAW_BIN='/usr/bin/true',LITGRAPH_PY_PREFIX=sys.base_prefix)
        self.command('-m','unittest','discover','-s','system/runtime','-p','test_*.py',env=env)

    def test_native_baseline_regressions(self):
        self.command('-m','unittest','discover','-s','baselines/runtime','-p','test_*.py')

    def test_ideascientist_rubrics(self):
        self.command('-m','unittest','discover','-s','benchmarks/ideascientist','-p','test_*.py')

    def test_benchmarks_prepare_offline_and_preserve_scope(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            tmp=Path(tmp)
            rows=[{'system':'synthetic','task_id':'agent-memory','domain':'Agent memory','idea_id':str(i),
                   'idea_text':json.dumps({'title':f'Offline fixture {i}','problem':'p','mechanism':'m'}),
                   'task_context':'Offline fixture; no scientific result','domain_ids':['agent-memory'],
                   'selector_top1':i==0} for i in range(5)]
            source=tmp/'cards.json';source.write_text(json.dumps(rows))
            self.command('benchmarks/run.py','reviewer','prepare','--input',source,'--out',tmp/'reviewer')
            self.command('benchmarks/run.py','interesting','prepare','--input',source,'--out',tmp/'interesting')
            m=json.loads((tmp/'interesting/manifest.json').read_text())
            payload=json.loads(next((tmp/'interesting/inputs').glob('*.json')).read_text())
            self.assertEqual([s['kind'] for s in payload['stages']],['read','score'])
            self.assertEqual(sum(x['selector_top1'] for x in payload['mapping']),1)
            self.assertEqual(m['scope'],'per_system_per_domain')
            self.command('baselines/run.py','prepare','--method','coi','--domains','agent-memory','--out',tmp/'coi')
            self.command('baselines/run.py','prepare','--method','ideascientist','--domains','agent-memory','--out',tmp/'isci')

    def test_ideascientist_uses_frozen_reviewer_evidence_and_selection(self):
        pipeline=module('fixture_reviewer',ROOT/'benchmarks/reviewer/pipeline.py')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            tmp=Path(tmp);source=tmp/'cards.json';reviewer=tmp/'reviewer'
            source.write_text(json.dumps([{'system':'fixture','task_id':'agent-memory','idea_id':'card-one',
                'domain_ids':['agent-memory'],'selector_top1':True,
                'idea_text':json.dumps({'title':'Fixture','problem':'p','mechanism':'original mechanism'})}]))
            pipeline.prepare(reviewer,source=source)
            manifest=pipeline.read(reviewer/'manifest.json');item=manifest['items'][0]
            packet=pipeline.read(reviewer/'inputs'/f"{item['id']}.json")
            packet['reference_materials']=[{'kind':'paper','doc_id':'paper:1','read_depth':'source_card',
                'content':{'title':'Frozen reference','insight':{'mechanism':'source mechanism'}}}]
            dest=reviewer/'evidence'/item['id'];pipeline.save(dest/'packet.json',packet)
            pipeline.save(dest/'receipt.json',{'packet_sha256':pipeline.sha(dest/'packet.json'),
                'input_sha256':item['input_sha256']})
            pipeline.prepare(tmp/'repeated',from_evaluation=reviewer)
            self.assertTrue(pipeline.read(tmp/'repeated/manifest.json')['items'][0]['selector_top1'])
            self.command('benchmarks/run.py','ideascientist','prepare','--input',reviewer,'--out',tmp/'isbench')
            prepared=pipeline.read(tmp/'isbench/manifest.json');job=prepared['jobs'][0]
            self.assertTrue(job['selector_top1'])
            request=pipeline.read(tmp/'isbench/inputs'/f"{job['id']}.json")
            self.assertIn('Frozen reference',request['novelty_current']['user'])
            self.assertIn('original mechanism',request['transfer']['mechanism'])

    def test_founder_rejects_incomplete_pairwise_judgments(self):
        b=module('portable_bench',ROOT/'benchmarks/run.py')
        payload={'expected_pairs':[['A1','T1'],['A2','T1']]}
        one={'card':'A1','target':'T1','level':0,'rationale':'unrelated'}
        with self.assertRaises(ValueError):b.validate_founder({'matches':[one]},payload)
        with self.assertRaises(ValueError):b.validate_founder({'matches':[one,one]},payload)
        b.validate_founder({'matches':[one,dict(one,card='A2')]},payload)

    def test_reviewer_failed_acquisition_does_not_launch_judges(self):
        pipeline=module('fixture_scheduler',ROOT/'benchmarks/reviewer/pipeline.py')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            tmp=Path(tmp);source=tmp/'cards.json';out=tmp/'reviewer'
            source.write_text(json.dumps([{'system':'fixture','task_id':'agent-memory','idea_id':'one',
                'domain_ids':['agent-memory'],'idea_text':'Offline scheduler fixture'}]))
            pipeline.prepare(out,source=source)
            failed=SimpleNamespace(pid=2147483647,poll=lambda:1)
            with patch.object(pipeline.subprocess,'Popen',return_value=failed) as launch, \
                 patch.object(pipeline.time,'sleep'),patch.object(pipeline,'report',return_value={}):
                pipeline.run(out,astra_limit=1,opus_limit=1)
            self.assertEqual(launch.call_count,1)
            jobs=list(pipeline.read(out/'state.json')['jobs'].values())
            self.assertEqual([j['status'] for j in jobs if j['stage']=='evidence'],['needs_attention'])
            self.assertTrue(all(j['status']=='pending' for j in jobs if j['stage']!='evidence'))

    def test_top1_uses_frozen_selector_even_when_another_card_scores_higher(self):
        b=module('top1_bench_entry',ROOT/'benchmarks/run.py')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            out=Path(tmp);payload={'mapping':[{'card_id':'card_01','idea_id':'one','selector_top1':True},
                                            {'card_id':'card_02','idea_id':'two','selector_top1':False}]}
            job={'id':'panel','system':'fixture','domain':'agent-memory','input_sha256':b.digest(payload)}
            b.save(out/'inputs/panel.json',payload)
            for judge in b.MODELS:
                value={'ledger':{'card_01':{'score':20},'card_02':{'score':90}}}
                root=out/'reviews/panel'/judge;b.save(root/'assessment.json',value)
                b.save(root/'receipt.json',{'input_sha256':b.digest(payload),'assessment_sha256':b.digest(value)})
            b.report(argparse.Namespace(out=out,benchmark='interesting'),{'protocol':'test','jobs':[job]})
            for group in json.loads((out/'results.json').read_text())['summary']:
                self.assertEqual(group['means']['interesting'],55)
                self.assertEqual(group['selector_top1_means']['interesting'],20)

    def test_founder_truth_and_input_preparation(self):
        b=module('founder_bench_entry',ROOT/'benchmarks/run.py')
        targets=[json.loads(s) for s in (ROOT/'benchmarks/founder/data/targets.jsonl').read_text().splitlines() if s]
        rubric=module('founder_rubric',ROOT/'benchmarks/founder/rubric.py')
        main=[t for t in targets if not t.get('supplementary')]
        self.assertEqual(len(main),69)
        truth=rubric.truth_for(main[:1]);self.assertTrue(truth[0]['mechanism'])
        task=main[0]['task_id'];cutoff=task.split(':')[0]
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            tmp=Path(tmp);source=tmp/'submission.json'
            source.write_text(json.dumps([{'system':'synthetic','task_id':task,
                'cards':[{'title':f'Fixture {i}','mechanism':'fixture'} for i in range(10)],
                'generation_protocol':{'web_access':False,'literature_before':cutoff,'generator_training_before':'2025-08-01'}}]))
            self.command('benchmarks/run.py','founder','prepare','--input',source,'--out',tmp/'founder')
            m=json.loads((tmp/'founder/manifest.json').read_text())
            self.assertEqual(m['expected_main_tasks'],58)
            self.assertEqual(m['expected_main_targets'],69)

if __name__=='__main__':unittest.main()
