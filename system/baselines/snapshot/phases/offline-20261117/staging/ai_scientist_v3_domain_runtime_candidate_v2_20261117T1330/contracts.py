from pathlib import Path
import hashlib,json,os
D=Path(__file__).resolve().parent;P=D.parents[1]
BASE=P/'staging/ai_scientist_v3_native_ideation_adaptation_v1'
MAT=P/'staging/ai_scientist_v3_domain_materials_v1_20261117T1315'
METHOD='ai_scientist_v3_native_ideation'
SCOPE='official-ai-scientist-v3-first-native-ideation-stage-common-corpus'
SOCKET='/tmp/insightpro-offline-model-20261117.sock'
BASE_SHA='48f15d30767f409559099295c2176e103aa9cacec8f74c9b4f65e24aa7fd25a1'
MAT_SHA='72f225aff17ea1835e013d3dac4c6826a972c651a0f417a65c5037e763bd5570'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()
def bound(ref):
 assert sha(ref['path'])==ref['sha256'],'Reference changed'
 return read(ref['path'])
def verify_manifest(expected):
 assert sha(D/'sealed_runtime_manifest.json')==expected
 m=read(D/'sealed_runtime_manifest.json')
 assert sha(BASE/'sealed_manifest.json')==BASE_SHA and sha(MAT/'sealed_preparation_manifest.json')==MAT_SHA
 for doc in [m,read(BASE/'sealed_manifest.json'),read(MAT/'sealed_preparation_manifest.json')]:
  for name,digest in {**doc.get('bindings',{}),**doc.get('source_bindings',{})}.items():assert sha(name)==digest,name
  for name,target in doc.get('symlinks',{}).items():assert Path(name).is_symlink() and os.readlink(name)==target
 assert sha(P/'inputs/corpus/corpus.sqlite')==m['corpus_sha256']
 return m
def plans():
 rows=read(MAT/'disabled_slot_bindings.json')['slots']
 for b in rows:
  if not b['preserve_existing_completed_slot']:
   b['prepared_native_task_dir_argument']=b['native_task_dir_argument']
   b['native_task_dir_argument']=str(Path(b['native_run'])/'task_source')
 return rows
def slot_plan(domain,slot):
 matches=[x for x in plans() if x['domain']==domain and x['slot']==slot]
 assert len(matches)==1 and not matches[0]['preserve_existing_completed_slot'],'Existing first slot stays frozen'
 return matches[0]
def registration(b,stage='native_generation'):
 row={'method':METHOD,'admission_id':b['admission_id'],'run_id':b['run_id'],'stage':stage,'root':b['output'],'fixture':False,'model':'gpt-6-astra','reasoning_effort':'xhigh','comparison_scope':SCOPE,'journal_format':'headless_transport_events_v1','journal_relative_root':'native'}
 if stage=='scoring':row.update(run_id=b['run_id']+'-external-CIS',root=str(P/'evaluations'/METHOD/b['domain']/f"slot-{b['slot']:02}"),journal_format='common_api_events_v1',journal_relative_root='.',native_source_run_id=b['run_id'])
 return row
def validate_admission(a,b,index_sha,manifest_sha,registry,review):
 expected={'schema':'sakana-domain-slot-admission-v2','enabled':True,'fixture':False,'method':METHOD,'domain':b['domain'],'slot':b['slot'],'output':b['output'],'run_id':b['run_id'],'admission_id':b['admission_id'],'mapping':b['mapping'],'mapping_sha256':b['mapping_sha256'],'domain_json':b['domain_json'],'domain_sha256':b['domain_sha256'],'model':'gpt-6-astra','reasoning_effort':'xhigh','api':'responses','model_socket':SOCKET,'shared_physical_request_cap':250,'comparison_scope':SCOPE,'runtime_manifest_sha256':manifest_sha,**{k:b[k] for k in ('task_source','task_context','native_run','native_task_dir_argument','isolated_home','global_memory_dir','conclusions_dir','journal','corpus_id','corpus_sha256')},'scoring_gate_open':False,'automatic_followup_slots':False,'external_CIS_feedback_to_native':False}
 assert all(a.get(k)==v for k,v in expected.items()),'Cross-domain/slot/model/runtime admission'
 assert review.get('status')=='accepted_v3_domain_runtime_package' and review.get('passed') is True and review.get('fixture') is not True and review.get('reviewer') and review.get('paid_calls')==0 and review.get('manifest_sha256')==manifest_sha and review.get('controller_index_sha256')==index_sha
 assert registry.get('schema')=='new-method-cost-registration-v1'
 assert sum(x==registration(b) for x in registry['registrations'])==1,'Exact costs not registered before launch'
 assert sum(x.get('root')==b['output'] for x in registry['registrations'])==1,'Duplicate cost root'
 assert b==slot_plan(b['domain'],b['slot']),'Unsealed context plan'
 assert b['task_context']==str(Path(b['output'])/'native/results/task')
 assert b['native_task_dir_argument']==str(Path(b['native_run'])/'task_source')
 mapping=read(b['mapping']);assert sha(b['mapping'])==b['mapping_sha256'] and sha(b['domain_json'])==b['domain_sha256']
 assert mapping['domain']==b['domain'] and all(sha(k)==v for k,v in mapping['bindings'].items())
 return True
