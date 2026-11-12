"""No-model regression checks for knowledge isolation, source evidence, and quotas."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BENCH=Path(__file__).resolve().parent.parent
SYSTEMS=BENCH
RUNTIME=Path(__file__).resolve().parent

class Conditions(unittest.TestCase):
    def test_all_four_workspaces_and_published_prompts(self):
        code=r'''
import tempfile,json
from pathlib import Path
import cli,single,prompts
from common import *
assert cli.check()['domain_count']==38
with tempfile.TemporaryDirectory(dir=os.environ['IDEAX_SCRATCH']) as tmp:
 run=Path(tmp)/'run';single.prepare(run,'agent-memory')
 content=(run/'initial_prompt.md').read_text()
 assert (run/'work/full_domain_context.jsonl').exists()==(ACCESS=='full')
 assert (run/'work/library_api.json').exists()==(ACCESS!='web')
 assert (run/'work/tools/library_client.py').exists()==(ACCESS!='web')
 assert read(run/'run.json')['injected_insights']>0 if ACCESS=='full' else read(run/'run.json')['injected_insights']==0
 for name in ('DISCUSS','RESPOND','SELECT'):
  value=getattr(prompts,name).format(author='author-01',own='c-001',domain='test')
  if ACCESS!='full': assert '/work/full_domain_context.jsonl' not in value
 if ACCESS=='api':
  assert '<complete_domain_context>' not in content and '公开网络访问可选' in content
 if ACCESS=='web':
  assert '<complete_domain_context>' not in content and 'BASE=' not in content
  assert '/api/v1/entries/' not in (SYSTEM/'prompts/blueprint.md').read_text()
print(json.dumps({'condition':CONDITION,'ok':True}))
'''
        for system in sorted(p for p in SYSTEMS.iterdir() if (p/'release.json').is_file()):
            env=dict(os.environ,IDEAX_CURRENT_SYSTEM=str(system))
            result=subprocess.run([sys.executable,'-B','-c',code],env=env,cwd=RUNTIME,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,system.name+': '+result.stderr)

    def test_api_cannot_validate_unobserved_hidden_context(self):
        code=r'''
import tempfile,hashlib,json
from pathlib import Path
from common import *
from access_policy import check_sources
import single
with tempfile.TemporaryDirectory(dir=os.environ['IDEAX_SCRATCH']) as tmp:
 run=Path(tmp)/'run';single.prepare(run,'agent-memory')
 card={'problem':'agent-memory-P0001','mechanism':'agent-memory-I0001'}
 assert check_sources(card,run)
 data={'ok':True,'data':[{'id':'agent-memory-P0001','kind':'problem','unit':'agent-memory'},{'id':'agent-memory-I0001','kind':'insight','unit':'agent-memory'}]}
 raw=json.dumps(data).encode();h=hashlib.sha256(raw).hexdigest();p=run/'work/out/api_responses';p.mkdir();(p/(h+'.json')).write_bytes(raw)
 # A source file without a recorded successful API response is not admissible.
 assert check_sources(card,run)
 log={'url':os.environ['LITGRAPH_API_BASE_URL']+'/api/v1/search','request_id':'test','attempt':1,'at':'test','status':200,'sha256':h}
 (run/'work/out/api_requests.jsonl').write_text(json.dumps(log)+'\n')
 assert not check_sources(card,run)
 card['problem']='other-domain-P0001';assert check_sources(card,run)
'''
        env=dict(os.environ,IDEAX_CURRENT_SYSTEM=str(SYSTEMS/'single-api'))
        r=subprocess.run([sys.executable,'-B','-c',code],env=env,cwd=RUNTIME,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_web_host_and_server_tool_exclusions(self):
        sys.path.insert(0,str(RUNTIME/'transport'))
        import api_gate
        self.assertTrue(api_gate.host_excluded('api.example.com.',{'api.example.com'}))
        self.assertTrue(api_gate.host_excluded('sub.api.example.com',{'api.example.com'}))
        self.assertTrue(api_gate.host_excluded('1.2.3.4',{'api.example.com'}))
        self.assertFalse(api_gate.host_excluded('arxiv.org',{'api.example.com'}))
        body=json.dumps({'tools':[{'type':'web_search'}]}).encode()
        self.assertIsNotNone(api_gate.forbidden_openai(body,False))

    def test_request_pools_are_separate_and_bounded(self):
        sys.path.insert(0,str(RUNTIME/'transport'))
        import quota
        saved=quota.ROOT
        with tempfile.TemporaryDirectory(dir=os.environ['IDEAX_SCRATCH']) as tmp:
            quota.ROOT=Path(tmp)
            (quota.ROOT/'control.json').write_text(json.dumps({'limits':dict.fromkeys(quota.LIMITS,2)}))
            a=quota.acquire('astra_generation');b=quota.acquire('astra_generation')
            self.assertIsNotNone(a);self.assertIsNotNone(b)
            self.assertIsNone(quota.acquire('astra_generation'))
            c=quota.acquire('astra_evaluation');d=quota.acquire('opus_evaluation')
            self.assertIsNotNone(c);self.assertIsNotNone(d)
            a.close();e=quota.acquire('astra_generation');self.assertIsNotNone(e)
            for f in (b,c,d,e):f.close()
        quota.ROOT=saved

if __name__=='__main__':unittest.main()
