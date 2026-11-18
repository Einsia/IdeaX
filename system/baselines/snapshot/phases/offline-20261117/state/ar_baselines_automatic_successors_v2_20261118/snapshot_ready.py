from pathlib import Path
import collections,json,sys,time
S=Path(__file__).resolve().parent;P=S.parents[1];sys.path.insert(0,str(P));import campaign as C
state=C.read(P/'state/campaign.json');methods=C.read(P/'state/methods.json');registry=C.read(P/'state/generation_recoveries.json');jobs=state['jobs'];rows=[];terminal=[]
for key,j in jobs.items():
 if j['kind']!='generation' or j['method'] not in ['insightagents','sciagents','cycleresearcher']:continue
 if C.alive(j.get('process')) or j['status'] in ['completed','native_failure']:continue
 spec=methods[j['method']];ready=C.ready(j,jobs,methods);recovery=C.ready_recovery(j,registry,methods);out=C.result_path(j).parent;candidate=None
 action=registry.get(key)
 if action and '--manifest' in action.get('command',[]):
  m=C.read(action['command'][action['command'].index('--manifest')+1],{});candidate=out/m.get('candidate_filename','original_transport_candidate_result.json')
 if candidate and candidate.exists() and C.read(candidate).get('status')=='completed':reason='completed_candidate_requires_native_terminal_acceptance';terminal.append({'job_key':key,'job':j,'candidate':str(candidate),'manifest':action['command'][action['command'].index('--manifest')+1]})
 elif (out/'terminal.json').exists():reason='native_terminal_requires_acceptance_or_finalization'
 elif ready or recovery:reason='ready_pending_scheduler_admission'
 elif j['status']=='pending':
  if not spec.get('enabled'):reason='method_disabled'
  elif j['domain'] not in spec.get('eligible_domains',[j['domain']]):reason='original_domain_graph_not_admitted'
  elif j['slot'] not in spec.get('eligible_slots_by_domain',{}).get(j['domain'],range(1,6)):reason='original_domain_first_slot_terminal_gate'
  else:reason='original_prior_slot_or_scope_gate'
 elif action and action.get('recovery_id') not in j.get('executed_recovery_ids',[]) and action.get('not_before_epoch',0)>time.time():reason='verified_failure_backoff'
 elif j['status']=='infrastructure_failure':reason='API_or_storage_failure_requires_strict_successor_or_evidence_repair'
 else:reason=j['status']
 rows.append({'job_key':key,'method':j['method'],'status':j['status'],'launches':j['launches'],'ready_fresh':ready,'ready_recovery':bool(recovery),'reason':reason,'recovery_due':None if not action else action.get('next_retry_at')})
capacity=C.read(P/'state/serialized_runtime_capacity_and_recovery_audit.json');owner=C.read(P/'state/ar_baselines_normal_recovery_owner_20261118T0020/health.json');data={'at':C.now(),'same_original_protocol_scope_only':True,'ready_not_started':[r for r in rows if r['ready_fresh'] or r['ready_recovery']],'rows':rows,'reason_counts':dict(collections.Counter(r['reason'] for r in rows)),'method_caps':{m:methods[m]['max_generation_workers'] for m in ['insightagents','sciagents','cycleresearcher']},'owner_process':owner['process'],'owner_kernel_locks':[line for line in Path('/proc/locks').read_text().splitlines() if f" {owner['process']['pid']} " in line], 'capacity_snapshot':capacity}
C.save(S/'ready_and_recovery_audit.json',data);C.save(S/'current_terminal_candidates.json',{'at':C.now(),'rows':terminal});print(json.dumps({'at':data['at'],'ready_not_started':len(data['ready_not_started']),'reason_counts':data['reason_counts'],'terminal_candidates':[r['job_key'] for r in terminal],'physical_http':capacity.get('physical_http_held_slots'),'pool':capacity.get('physical_http_pool_size'),'owner':owner['process']},indent=2))
