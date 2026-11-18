"""Pure admission checks plus actual local native fixture replay. No paid calls."""
import ast,copy,datetime,json,os,subprocess,sys
from pathlib import Path
from contracts import *
from result_export import export_result,save
from activate import pending_jobs,initial_eligibility,method_updates,C,verify_proof
from scheduler_entry import pending_terminal_matches
from dynamic_report import summarize,render

def main():
 checks={};out=D/'preflight';out.mkdir(exist_ok=False)
 for f in D.glob('*.py'):ast.parse(f.read_text())
 checks['all_candidate_python_parses']=True
 snapshots={};native_checks={}
 for domain,slot in [('agent-memory',2),('adaptive-compute-termination',1)]:
  run=D/'recording_fixtures'/f'{domain}-slot{slot:02}';b=slot_plan(domain,slot);group={}
  native_checks[domain]=group
  before=read(run/'pre_normalization/before.json');capture=read(run/'pre_normalization/capture_receipt.json');launcher=read(run/'launcher.json')
  group['fresh_empty_native_history']=before['output_files_absent'] and launcher['initial_history_empty']
  group['original_prompt_and_skills_exact']=capture['instructions_unchanged'] and all(sha(p)==h for p,h in before['instruction_bindings'].items())
  group['native_normalization_without_external_repair']=capture['capture_stage']=='after real Headless returned, before original idea.sh postprocess' and not capture['external_repair']
  command=read(run/'native_command.json')
  group['actual_per_run_task_source_argument']=command[command.index('--task-dir')+1]==str(run/'task_source')
  group['cycle_one_and_memory_fresh']=command[command.index('--cycle-index')+1]=='1' and (run/'pre_normalization/memory.jsonl').read_bytes()==b''
  group['exact_selected_domain_materials']=all(sha(run/'task_source'/f.relative_to(b['task_source']))==sha(f)==sha(run/'results/task'/f.relative_to(b['task_source'])) for f in Path(b['task_source']).rglob('*') if f.is_file())
  group['first_native_script_success']=read(run/'process_receipt.json')['returncode']==0
  events=[json.loads(s) for s in (run/'transport/events.jsonl').read_text().splitlines()];starts=[e for e in events if e['event']=='attempt_start'];ends=[e for e in events if e['event']=='attempt_end']
  group['full_native_recording_five_requests_two_threads']=len(starts)==len(ends)==5 and len({e['native_thread_id'] for e in starts})==2
  group['all_requests_fixture_no_bridge']=all(e['fixture'] is True and e['bridge_request_id'] is None for e in events)
  group['identities_unique_and_per_run']=len({e['physical_attempt_id'] for e in starts})==5 and all(e['run_id']=='fixture-'+domain+f'-slot{slot:02}' and e['admission_id']=='fixture-isolated-'+domain+f'-slot{slot:02}' for e in events)
  group['model_and_effort_unchanged']=all(e['model']=='gpt-6-astra' and e['reasoning_effort']=='xhigh' for e in events)
  group['attempt_starts_unknown_usage']=all(e['usage'] is None and e['usage_known'] is False for e in starts)
  requests=[read(f) for f in sorted((run/'transport').glob('*/request.json'))]
  tooltext='\n'.join(str(x.get('output')) for r in requests for x in r.get('input',[]) if x.get('type','').endswith('_output'))
  group['real_skill_and_task_reads']='name: create-idea' in tooltext and 'name: memory-log' in tooltext and (Path(b['task_source'])/'task.md').read_text().splitlines()[1] in tooltext
  group['actual_tools_write_and_readback']='File written.' in tooltext and 'fixture_0001' in tooltext
  group['actual_task_mutation_rejected']='EXPECTED_READONLY_REJECTION' in tooltext
  boundary=read(run/'agent_runtime_boundary.json');outer=read(run/'offline_boundary.json');mounts={line.split()[4]:line.split()[5].split(',') for line in boundary['mountinfo'].splitlines()}
  group['private_network_no_default_route']=boundary['netns']==outer['network_namespace'] and boundary['netns']!=os.readlink('/proc/self/ns/net') and not boundary['route'].splitlines()[1:]
  group['real_model_socket_absent']=not outer['model_socket_present'] and not launcher['shared_model_socket_mounted'] and not launcher['paid_model_calls_allowed']
  group['all_task_instruction_config_readonly']=all('ro' in mounts.get(str(p),[]) for p in [run,run/'task_source',run/'results/task',run/'results/idea/idea_prompt.md',run/'results/idea/.codex/skills',run/'home/.codex/config.toml',Path('/isolated_home/.codex/config.toml')])
  group['only_results_home_data_writable']=all('rw' in mounts.get(str(p),[]) for p in [run/'results',run/'home',Path('/isolated_home')])
  group['no_capabilities_seccomp_enforced']='Seccomp:\t2' in boundary['status'] and 'CapEff:\t0000000000000000' in boundary['status'] and 'NoNewPrivs:\t1' in boundary['status']
  group['all_runtime_processes_share_private_network']=all(proc['netns']==boundary['netns'] for f in (run/'transport').glob('*/process_snapshot.json') for proc in read(f))
  identity={'method':METHOD,'domain':domain,'slot':f'slot-{slot:02}','run_id':'fixture-'+domain+f'-slot{slot:02}','admission_id':'fixture-isolated-'+domain+f'-slot{slot:02}','comparison_scope':SCOPE,'data_version':'offline-common-corpus-20261117-v1','corpus_id':b['corpus_id'],'corpus_sha256':b['corpus_sha256']}
  target=out/(domain+'_fixture_export');target.mkdir();result=export_result(run,target,identity,0,fixture=True);card=read(target/'external_CIS_input.json')
  group['full_raw_bundle_and_rubrics_export']=card['idea_bundle']==read(run/'results/idea/idea_bundle.json') and card['target_rubrics']==read(run/'results/idea/target_rubrics.json') and card['LLM_summarization'] is False
  group['official_artifact_checker_passed']=result.get('artifact_replay_passed') is True
  group['fixture_export_never_canonical_or_scoring_ready']=result['status']=='native_terminal_pending_independent_acceptance' and result['fixture'] is True and result['scoring_gate_open'] is False
  group['original_fallback_memory_preserved']='appended fallback idea-step memory entry' in (run/'native_script.log').read_text() and (run/'results/memory.jsonl').stat().st_size>0
  snapshots[domain]={'run_id':identity['run_id'],'home':str(run/'home'),'task_sha256':sha(run/'task_source/task.md'),'thread_ids':sorted({e['native_thread_id'] for e in starts})}
  for key,value in group.items():checks[domain+':'+key]=value
 checks['two_domains_have_distinct_task_bytes']=len({s['task_sha256'] for s in snapshots.values()})==2
 checks['two_contexts_have_distinct_homes_and_thread_ids']=len({s['home'] for s in snapshots.values()})==2 and set(snapshots['agent-memory']['thread_ids']).isdisjoint(snapshots['adaptive-compute-termination']['thread_ids'])
 b=slot_plan('agent-memory',2);review={'status':'accepted_v3_domain_runtime_package','passed':True,'fixture':False,'reviewer':'in-memory-fixture-only','paid_calls':0,'manifest_sha256':'fixture-manifest-sha','controller_index_sha256':'fixture-index-sha'}
 a={**b,'schema':'sakana-domain-slot-admission-v2','fixture':False,'enabled':True,'runtime_manifest_sha256':'fixture-manifest-sha'};registry={'schema':'new-method-cost-registration-v1','registrations':[registration(b)]}
 def admit(a=a,b=b,registry=registry,review=review):return validate_admission(a,b,'fixture-index-sha','fixture-manifest-sha',registry,review)
 checks['pure_complete_admission_validates']=admit()
 def rejected(fn):
  try:fn();return False
  except (AssertionError,ValueError,KeyError,OSError,TypeError):return True
 changes={'fixture':True,'enabled':False,'domain':'latent-reasoning','slot':3,'output':b['output']+'wrong','run_id':'wrong','admission_id':'wrong','task_source':str(MAT/'task_inputs/latent-reasoning'),'task_context':b['task_context']+'wrong','native_task_dir_argument':b['task_context'],'isolated_home':b['isolated_home']+'wrong','global_memory_dir':b['global_memory_dir']+'wrong','conclusions_dir':b['conclusions_dir']+'wrong','mapping_sha256':'bad','domain_sha256':'bad','model':'wrong','reasoning_effort':'low','api':'chat','model_socket':'/wrong.sock','shared_physical_request_cap':251,'comparison_scope':'wrong','runtime_manifest_sha256':'wrong','external_CIS_feedback_to_native':True,'automatic_followup_slots':True,'scoring_gate_open':True}
 for field,value in changes.items():checks['reject_admission_'+field]=rejected(lambda field=field,value=value:admit(a={**a,field:value}))
 for field,value in [('fixture',True),('passed',False),('paid_calls',1),('manifest_sha256','wrong'),('controller_index_sha256','wrong')]:checks['reject_review_'+field]=rejected(lambda field=field,value=value:admit(review={**review,field:value}))
 checks['reject_missing_accounting']=rejected(lambda:admit(registry={'schema':registry['schema'],'registrations':[]}))
 checks['reject_duplicate_accounting']=rejected(lambda:admit(registry={'schema':registry['schema'],'registrations':registry['registrations']*2}))
 checks['reject_cross_context_plan']=rejected(lambda:admit(b={**b,'isolated_home':'/wrong/home'}))
 checks['reject_original_completed_first_slot']=rejected(lambda:slot_plan('agent-memory',1))
 checks['reject_cross_domain_first_native_proof']=rejected(lambda:verify_proof({'path':str(P/'state/ai_scientist_v3_first_controlled_slot/native_terminal_acceptance.json'),'sha256':sha(P/'state/ai_scientist_v3_first_controlled_slot/native_terminal_acceptance.json')},'adaptive-compute-termination'))
 state=read(P/'state/campaign.json');methods=read(P/'state/methods.json');old=copy.deepcopy(state);jobs=pending_jobs();candidate=copy.deepcopy(state);candidate['jobs'].update(jobs)
 fakeplan={'command':['fixture-only'],'preserved_first_native_acceptance':{'path':'fixture-only','sha256':'fixture-only'}}
 changed=copy.deepcopy(methods);changed[METHOD].update(method_updates(fakeplan,{'path':'fixture-only','sha256':'fixture-only'},methods[METHOD]))
 ready=[j for j in jobs.values() if j['kind']=='generation' and C.ready(j,candidate['jobs'],changed)]
 checks['only_41_initial_new_slots_ready']=len(ready)==41 and sum(j['domain']=='agent-memory' for j in ready)==4 and all(j['slot']==1 for j in ready if j['domain']!='agent-memory')
 checks['other_37_domains_remaining_slots_withheld']=all(not C.ready(j,candidate['jobs'],changed) for j in jobs.values() if j['kind']=='generation' and j['domain']!='agent-memory' and j['slot']>1)
 checks['189_generation_plus_189_card_no_novelty']=len(jobs)==378 and sum(j['kind']=='generation' for j in jobs.values())==189 and sum(j['kind']=='card' for j in jobs.values())==189
 checks['all_new_cards_withheld_before_native_acceptance']=all(not C.ready(j,candidate['jobs'],changed) for j in jobs.values() if j['kind']=='card')
 checks['all_prior_jobs_preserved']=all(candidate['jobs'][key]==value for key,value in old['jobs'].items()) and state==old
 job={'method':METHOD,'kind':'generation','domain':b['domain'],'slot':b['slot'],'process':{'pid':-1,'start':'fixture'}};binding={'method':METHOD,'domain':b['domain'],'slot':'slot-02','run_id':b['run_id'],'admission_id':b['admission_id'],'comparison_scope':SCOPE,'fixture':False}
 value={**binding,'status':'native_terminal_pending_independent_acceptance','native_returncode':0,'artifact_replay_passed':True,'scoring_gate_open':False,'native_stage_only':True,'native_run':b['native_run']};receipt={'returncode':0,'mode':'controlled_real'}
 checks['exact_terminal_pending_recognized']=pending_terminal_matches(job,value,binding,receipt,b)
 for field,v in [('fixture',True),('domain','wrong'),('run_id','wrong'),('admission_id','wrong'),('status','native_failure'),('status','infrastructure_failure'),('native_returncode',1),('artifact_replay_passed',False)]:checks['pending_reject_'+field+'_'+str(v)]=not pending_terminal_matches(job,{**value,field:v},binding,receipt,b)
 checks['pending_reject_other_method']=not pending_terminal_matches({**job,'method':'sciagents'},value,binding,receipt,b)
 checks['pending_reject_no_process']=not pending_terminal_matches({**job,'process':None},value,binding,receipt,b)
 preview=summarize(candidate,changed);save(D/'STATUS_preview.json',preview);(D/'STATUS_preview.md').write_text(render(preview))
 current=summarize(state,methods);save(out/'current_state_report_readonly.json',current)
 checks['dynamic_report_all_nine_methods']=len(preview['methods'])==9
 checks['dynamic_report_legacy_schema_retained']=preview['expected_slots']==1330 and all({'method','source_status','enabled','generation','target','cis_completed','novelty_panels_completed','terminal_infrastructure_exclusions'}<=set(r) for r in preview['methods'])
 rows={r['method']:r for r in preview['methods']}
 checks['retired_AI_not_active_target']=rows['ai_researcher']['retired_history_only'] and rows['ai_researcher']['target_generation_slots']==0
 checks['v3_additional_not_main']=rows[METHOD]['main_comparison_included'] is False and preview['additional_target_generation_slots']==190
 checks['insight_actual_status_and_blocker_visible']=rows['insightagents']['source_status']==methods['insightagents']['status'] and rows['insightagents']['blocker']==methods['insightagents'].get('blocker')
 checks['Sci_matched_target190_history_separate']=rows['sciagents']['scope_breakdown']['matched-domain-abstract-graph']['target_slots']==190 and rows['sciagents']['scope_breakdown']['legacy-original-graph-transfer']['target_slots'] is None
 checks['preview_does_not_mutate_input_jobs']=candidate['jobs']=={**old['jobs'],**jobs}
 checks['live_state_no_new_v3_jobs']=not any(k in state['jobs'] for k in jobs)
 save(D/'preflight_acceptance.json',{'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':all(checks.values()),'checks':checks,'paid_calls':0,'network_calls':0,'fixture':True,'live_state_mutations':0,'fixtures':snapshots,'source_bindings':{str(f):sha(f) for f in D.glob('*.py')},'excluded_earlier_zero_call_fixture':'recording_fixtures_attempt01_source_boundary_rejected: original idea.sh rejected canonical task inside results before any transport request'})
 print(json.dumps({'passed':sum(checks.values()),'failed':[k for k,v in checks.items() if not v],'paid_calls':0}))
 if not all(checks.values()):raise SystemExit(1)
if __name__=='__main__':main()
