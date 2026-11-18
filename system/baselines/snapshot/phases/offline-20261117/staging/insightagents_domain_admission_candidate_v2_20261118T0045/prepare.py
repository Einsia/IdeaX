"""Prepare only private sealed files and disabled exact-slot admission candidates."""
from pathlib import Path
import argparse,copy,json
from evidence import encode,sha
ROOT=Path(__file__).resolve().parent;PHASE=ROOT.parents[1]
OLD=PHASE/'staging/insightagents_local_recommendation_adapter_v1'
def freeze(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(encode(v))
def ref(p):return {'path':str(p),'sha256':sha(p)}
def seal():
    value=json.loads((OLD/'sealed_manifest.json').read_text())
    assert all(sha(r['path'])==r['sha256'] for r in value['bound_files'])
    for f in (OLD/'native').rglob('*'):
        if f.is_file():assert sha(f)==sha(ROOT/'native'/f.relative_to(OLD/'native'))
    assert sha(ROOT/'adapter.py')==sha(OLD/'adapter.py') and sha(ROOT/'local_client.py')==sha(OLD/'local_client.py')
    stream=PHASE/'state/insightagents_stream_continuation_v5/stream_transport.py';assert sha(stream)==sha(ROOT/'stream_transport.py')
    files=[f for f in ROOT.rglob('*') if f.is_file() and f.suffix=='.py']
    value['bound_files']+= [ref(f) for f in files]+[ref(OLD/'sealed_manifest.json'),ref(stream)]
    value.update(status='candidate_disabled_pending_independent_review',production_launch_enabled=False,only_controlled_target=None,original_target_slots=190,already_accepted_slots_excluded=['agent-memory/slot-01'],initial_release='37 new domains slot01 plus accepted agent-memory slots02-05',later_slot_rule='same-domain real full native terminal proof before each domain slots02-05',transport='unchanged_v5_responses_stream_reassembly_fresh_requests_original_sdk_retries3',native_source_and_prompt_changes=False,source_manifest=ref(OLD/'sealed_manifest.json'))
    freeze(ROOT/'sealed_manifest.json',value)
def admissions(destination,review=None,enabled=False,domain_acceptances=None):
    manifest=ROOT/'sealed_manifest.json';m=json.loads(manifest.read_text());dest=Path(destination);assert not dest.exists();index={};registrations=[];initial=[];held=[]
    proof=PHASE/'state/ar_baselines_insight_completed_publication_20261117T1632/postpublication_audit/proof.json'
    accepted={'agent-memory':ref(proof),**(domain_acceptances or {})}
    for domain,topic in m['topic_mapping']['domains'].items():
        for i in range(1,6):
            if domain=='agent-memory' and i==1:continue
            slot=f'slot-{i:02}';out=PHASE/'runs/insightagents'/domain/slot;d=dest/domain/slot
            row={'method':'insightagents','admission_id':f'insightagents-{domain}-slot{i:02}-common38-v1-20261118','run_id':f'insightagents-{domain}-slot{i:02}-native-common38-v1-20261118','stage':'native_generation','root':str(out),'fixture':False,'model':'gpt-6-astra','reasoning_effort':'xhigh','comparison_scope':m['comparison_scope'],'journal_format':'native_attempt_journal_v1'}
            ready=i==1 or domain in accepted;arm=enabled and ready
            receipt={'schema':'insightagents-original-slot-admission-v2','enabled':arm,'method':'insightagents','domain':domain,'slot':slot,'output':str(out),'comparison_scope':m['comparison_scope'],'fixture':False,'purpose':'original-native-generation','manifest_sha256':sha(manifest),'source_commit':m['source_commit'],'model':'gpt-6-astra','reasoning_effort':'xhigh','api':'responses','corpus_sha256':m['corpus_sha256'],'topic_sha256':topic['topic_sha256'],'scoring_gate_open':False,'automatic_followup_slots':False,'native_budget_and_retry_changes':False,'new_context':True,'run_id':row['run_id'],'admission_id':row['admission_id'],'model_socket':'/tmp/insightpro-offline-model-20261117.sock','independent_review':review,'domain_terminal_acceptance':accepted.get(domain) if i>1 else None}
            freeze(d/'admission.json',receipt);ad=ref(d/'admission.json')
            command=[m['python_executable'],str(ROOT/'launcher.py'),'--output',str(out),'--model-socket',receipt['model_socket'],'--manifest',str(manifest),'--domain',domain,'--slot',slot,'--admission-receipt',ad['path'],'--admission-sha256',ad['sha256']]
            c={'schema':'insightagents-original-slot-host-v2','fixture':False,'domain':domain,'slot':slot,'domain_json':topic['domain_source'],'output':str(out),'model_socket':receipt['model_socket'],'manifest':ref(manifest),'admission':ad,'accounting_registration':row,'command':command,'bindings':{str(f):sha(f) for f in [manifest,ROOT/'dispatch.py',ROOT/'launcher.py',d/'admission.json',Path(topic['domain_source'])]}}
            freeze(d/'host_contract.json',c);index[domain+'/'+slot]=ref(d/'host_contract.json');registrations.append(row);(initial if ready else held).append(domain+'/'+slot)
    assert len(index)==189 and len(initial)>=41
    freeze(dest/'index.json',{'contracts':index,'initial_release_ready_after_independent_package_acceptance':initial,'held_for_same_domain_terminal':held,'enabled':enabled,'registration_does_not_authorize_launch':True})
    freeze(dest/'accounting_registrations.json',{'registrations':registrations,'live_registry_mutated':False})
    freeze(dest/'dispatch_command.json',{'command':[m['python_executable'],str(ROOT/'dispatch.py'),'--contracts',str(dest)],'append_exact_domain_json_and_output_by_scheduler':True,'live_shared_state_mutated':False})
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['seal','admissions']);ap.add_argument('--destination');ap.add_argument('--review');ap.add_argument('--enabled',action='store_true');ap.add_argument('--domain-acceptances');a=ap.parse_args()
    if a.action=='seal':seal()
    else:
        assert not a.enabled or a.review,'Enabled private contracts require concrete independent review'
        admissions(a.destination,ref(a.review) if a.review else None,a.enabled,json.loads(Path(a.domain_acceptances).read_text()) if a.domain_acceptances else None)
