"""Seal only this candidate and prepare reviewed-plan inputs; never touch live state."""
import datetime,json,os
from contracts import *
from result_export import save
from activate import initial_eligibility

def ref(path):return {'path':str(path),'sha256':sha(path)}
def main():
 assert not (D/'sealed_runtime_manifest.json').exists(),'Candidate already sealed'
 check=read(D/'preflight_acceptance.json');assert check['passed'] is True and check['paid_calls']==0
 bindings={str(f):sha(f) for f in sorted(D.glob('*.py'))}
 bindings.update({str(D/'preflight_acceptance.json'):sha(D/'preflight_acceptance.json')})
 dependencies=[P/'campaign.py',P/'offline_gates.py',P/'scoring/revisions/new-method-accounting-v2-20261117/accounting_new_methods.py',Path('/home/liuhanzuo/new-ar-baseline-survey-20261117/review_tools/check_sakana_artifacts.py')]
 manifest={'schema':'sakana-domain-runtime-seal-v2','method':METHOD,'comparison_scope':SCOPE,'source_commit':'c95861ee97d2bc60a61de5fe4609329482c00a7d','bindings':bindings,'source_bindings':{str(f):sha(f) for f in dependencies},'symlinks':{str(f):os.readlink(f) for f in D.iterdir() if f.is_symlink()},'corpus_sha256':plans()[0]['corpus_sha256'],'base_manifest':ref(BASE/'sealed_manifest.json'),'material_manifest':ref(MAT/'sealed_preparation_manifest.json'),'task_argument_amendment':'Each fresh slot uses native/task_source as read-only canonical input, outside native/results, as required by unchanged official idea.sh. The independent staged model view remains native/results/task. Frozen material bytes and all original prompts remain unchanged.','paid_calls':0}
 save(D/'sealed_runtime_manifest.json',manifest);manifest_sha=sha(D/'sealed_runtime_manifest.json')
 verify_manifest(manifest_sha)
 admissions={};directory=D/'slot_admissions';directory.mkdir(exist_ok=False)
 for b in plans():
  if b['preserve_existing_completed_slot']:continue
  a={**b,'schema':'sakana-domain-slot-admission-v2','enabled':True,'fixture':False,'runtime_manifest_sha256':manifest_sha,'launch_requires':'Exact reviewed candidate activation in original primary scheduler; this file alone does not admit a job.'}
  path=directory/(b['domain']+f"__{b['slot']:02}.json");save(path,a);admissions[f"{b['domain']}/slot-{b['slot']:02}"]=ref(path)
 save(D/'controller_index.json',{'schema':'sakana-domain-controller-index-v2','fixture':False,'method':METHOD,'runtime_manifest_sha256':manifest_sha,'admissions':admissions,'independent_review_source':'methods[METHOD].runtime_independent_review must bind this exact index, runtime manifest and activation plan','preserve_first_run_id':'ai-scientist-v3-agent-memory-slot01-native-20261117'})
 index_ref=ref(D/'controller_index.json');command=['/usr/bin/python3','-B',str(D/'host_launch.py'),'--controller-index',index_ref['path'],'--controller-index-sha256',index_ref['sha256']]
 receipt={'protocol_id':'offline-common-corpus-20261117','passed':True,'checks':{'fresh_context':True,'native_pipeline_preserved':True,'offline_literature_adapter':True,'model_astra_xhigh':True},'comparison_scope':SCOPE,'method':METHOD,'command':command,'bindings':{**bindings,**manifest['source_bindings'],str(D/'sealed_runtime_manifest.json'):manifest_sha,str(D/'controller_index.json'):index_ref['sha256'],str(MAT/'sealed_preparation_manifest.json'):MAT_SHA,str(BASE/'sealed_manifest.json'):BASE_SHA},'paid_calls':0,'live_native_expansion_verified':False}
 save(D/'offline_receipt.json',receipt)
 plan={'schema':'sakana-domain-expansion-plan-v2','fixture':False,'method':METHOD,'comparison_scope':SCOPE,'main_comparison_included':False,'runtime_manifest_sha256':manifest_sha,'controller_index':index_ref,'command':command,'offline_receipt':ref(D/'offline_receipt.json'),'initial_eligible_slots_by_domain':initial_eligibility(),'new_generation_jobs':189,'new_card_jobs':189,'new_novelty_jobs':0,'capacity':{'generation':230,'scoring':20,'physical_requests':250},'accounting_implementation':ref(dependencies[2]),'accounting_registrations':[registration(b,stage) for b in plans() if not b['preserve_existing_completed_slot'] for stage in ('native_generation','scoring')],'preserved_first_native_acceptance':ref(P/'state/ai_scientist_v3_first_controlled_slot/native_terminal_acceptance.json'),'preserved_first_score_acceptance':ref(P/'state/ai_scientist_v3_first_score/terminal_acceptance.json'),'activation_directory':str(P/'state/ai_scientist_v3_common38_activation_v2_20261117'),'automatic_followup_slots':False,'paid_calls_by_preparer':0}
 save(D/'activation_plan.json',plan)
 save(D/'independent_review_requirements.json',{'schema':'review-response-requirements-not-an-acceptance','passed':False,'fixture':True,'expected_fields':{'status':'accepted_v3_domain_runtime_package','passed':True,'fixture':False,'paid_calls':0,'reviewer':'REQUIRED: independent reviewer identity','manifest_sha256':manifest_sha,'controller_index_sha256':index_ref['sha256'],'plan_sha256':sha(D/'activation_plan.json'),'activation_script_sha256':sha(D/'activate.py')},'note':'This is the required response schema, not an acceptance. Independent reviewer must create a separate bound review after checking the candidate.'})
 print(json.dumps({'runtime_manifest_sha256':manifest_sha,'controller_index_sha256':index_ref['sha256'],'plan_sha256':sha(D/'activation_plan.json'),'slot_admissions':len(admissions),'paid_calls':0}))
if __name__=='__main__':main()
