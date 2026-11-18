"""Keep the original scheduler; replace reporting and exact v3 pending recognition."""
import sys
from contracts import P,METHOD,SCOPE,read,sha,slot_plan
sys.path.insert(0,str(P))
import campaign as C
from dynamic_report import report
original_refresh=C.refresh

def pending_terminal_matches(job,value,binding,process_receipt,plan):
 expected={'method':METHOD,'domain':plan['domain'],'slot':f"slot-{plan['slot']:02}",'run_id':plan['run_id'],'admission_id':plan['admission_id'],'comparison_scope':SCOPE,'fixture':False}
 return (job.get('process') is not None and job.get('method')==METHOD and job.get('kind')=='generation'
  and job.get('domain')==plan['domain'] and job.get('slot')==plan['slot']
  and all(value.get(k)==v and binding.get(k)==v for k,v in expected.items())
  and value.get('status')=='native_terminal_pending_independent_acceptance'
  and value.get('native_returncode')==0 and value.get('artifact_replay_passed') is True
  and value.get('scoring_gate_open') is False and value.get('native_stage_only') is True
  and value.get('native_run')==plan['native_run']
  and process_receipt.get('returncode')==0 and process_receipt.get('mode')=='controlled_real')

def refresh(job):
 if job.get('method')==METHOD and job.get('kind')=='generation' and not C.alive(job.get('process')):
  try:
   plan=slot_plan(job['domain'],job['slot']);out=C.result_path(job).parent
   value=read(out/'result.json');binding=read(out/'run_binding.json');receipt=read(out/'native/process_receipt.json')
   if pending_terminal_matches(job,value,binding,receipt,plan):
    card=read(out/'external_CIS_input.json')
    if card.get('fixture') is False and card.get('run_id')==plan['run_id'] and card.get('admission_id')==plan['admission_id'] and card.get('source_bindings') and all(sha(p)==h for p,h in card['source_bindings'].items()):
     job['status']='native_terminal_pending_acceptance';return
  except (OSError,ValueError,KeyError,AssertionError,TypeError):pass
 return original_refresh(job)

if __name__=='__main__':
 C.refresh=refresh;C.report=report;C.supervise()
