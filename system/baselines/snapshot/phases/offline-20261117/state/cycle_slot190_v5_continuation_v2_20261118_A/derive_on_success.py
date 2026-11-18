"""Prepare an immutable ten-reviewer package automatically after the real canary succeeds.

No model transport is created; no owner queue, activation, campaign or publication is changed.
The coordinator owns the independent admission and existing normal-owner registration.
"""
from pathlib import Path
import argparse,datetime,json,time
import adapter_v5 as A
import prepare
S=A.S;P=A.P
def tick(config,health,package):
 cfg=A.read(config);assert cfg['job_key']=='cycleresearcher__ai-control-deception__05__generation' and cfg['physical_attempt_budget']==1
 if not health.exists():return {'status':'waiting_real_canary_health','model_calls':0}
 h=A.read(health)
 if h.get('success') is not True:return {'status':'canary_failed_checkpoint_held','native_zero_eligible':False,'next_retry_at':h.get('next_retry_at'),'model_calls':0}
 assert h['passed'] and h['real_gateway_required'] and h['probe_done'] and h['reviewer_stage_entered'] is False
 if (package/'manifest.json').exists():
  m=A.read(package/'manifest.json');assert m['fixture'] is False and m['canary_health']==prepare.ref(health) and m['canary_owner_config']==prepare.ref(config)
  assert all(A.sha(p)==v for p,v in A.read(package/'source_bindings.json').items())
 else:m=prepare.build(package,P/'runs/cycleresearcher/ai-control-deception/slot-05',health,canary_config=config)
 result={'status':'ten_original_reviewers_ready_for_coordinator_admission','manifest':prepare.ref(package/'manifest.json'),'owner_config':prepare.ref(package/'owner_config.json'),'source_bindings':prepare.ref(package/'source_bindings.json'),'admission_template':prepare.ref(package/'admission_template.json'),'normal_owner':str(P/'state/ar_baselines_normal_recovery_owner_20261118T0020/owner_v2.py'),'physical_attempt_budget':10,'same_slot':True,'new_sample':False,'model_calls':0,'shared_state_changed':False}
 ready=package/'ready.json'
 if not ready.exists():prepare.save(ready,result)
 return result
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--canary-owner-config',type=Path,required=True);ap.add_argument('--canary-health',type=Path,required=True);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--watch',action='store_true');args=ap.parse_args()
 while True:
  r=tick(args.canary_owner_config.resolve(),args.canary_health.resolve(),args.package.resolve());print(json.dumps(r),flush=True)
  if not args.watch or r['status']!='waiting_real_canary_health':return
  time.sleep(10)
if __name__=='__main__':main()
