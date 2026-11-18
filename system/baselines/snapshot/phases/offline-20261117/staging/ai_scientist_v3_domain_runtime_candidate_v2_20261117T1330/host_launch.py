"""Scheduler-only per-slot handoff; no automatic followup, retries or scoring."""
import argparse,datetime,json,subprocess
from pathlib import Path
from contracts import *
from runtime_launch import build_command
from result_export import export_result,save

def verify(index_path,index_sha,domain_json,output):
 index=bound({'path':index_path,'sha256':index_sha})
 assert index['schema']=='sakana-domain-controller-index-v2' and index['fixture'] is False
 domain=read(domain_json)['id'];out=Path(output).resolve();slot=int(out.name.removeprefix('slot-'))
 b=slot_plan(domain,slot)
 assert str(out)==b['output'] and str(Path(domain_json).resolve())==b['domain_json']
 spec=read(P/'state/methods.json')[METHOD]
 key=f'{domain}/slot-{slot:02}';a=bound(index['admissions'][key]);review=bound(spec['runtime_independent_review'])
 validate_admission(a,b,index_sha,index['runtime_manifest_sha256'],read(P/'state/new_method_accounting/registered.json'),review)
 verify_manifest(index['runtime_manifest_sha256'])
 assert spec['enabled'] and slot in spec['eligible_slots_by_domain'].get(domain,[]) and spec['max_generation_workers']>0
 assert spec['command']==['/usr/bin/python3','-B',str(D/'host_launch.py'),'--controller-index',str(Path(index_path).resolve()),'--controller-index-sha256',index_sha]
 assert Path(SOCKET).is_socket() and not out.exists(),'Existing run requires explicit recovery'
 return a,b,index

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--controller-index',required=True);ap.add_argument('--controller-index-sha256',required=True);ap.add_argument('--domain-json',required=True);ap.add_argument('--output-dir',required=True);args=ap.parse_args()
 a,b,index=verify(args.controller_index,args.controller_index_sha256,args.domain_json,args.output_dir)
 output=Path(b['output']);output.mkdir(parents=True,exist_ok=False)
 with (output/'native_launch_claim.json').open('x') as f:json.dump({'run_id':b['run_id'],'admission_id':b['admission_id'],'at':datetime.datetime.now(datetime.timezone.utc).isoformat()},f)
 identity={'method':METHOD,'domain':b['domain'],'slot':f"slot-{b['slot']:02}",'comparison_scope':SCOPE,'data_version':'offline-common-corpus-20261117-v1','corpus_id':b['corpus_id'],'corpus_sha256':b['corpus_sha256'],'run_id':b['run_id'],'admission_id':b['admission_id']}
 save(output/'input_material_version.json',{**identity,'mapping':b['mapping'],'mapping_sha256':b['mapping_sha256'],'external_CIS_feedback_to_native':False})
 save(output/'run_binding.json',{**identity,'fixture':False,'main_comparison_included':False,'native_cycle_index':1,'journal_relative_root':'native','runtime_manifest_sha256':index['runtime_manifest_sha256'],'controller_index':args.controller_index,'controller_index_sha256':args.controller_index_sha256,'domain_json':b['domain_json'],'domain_sha256':b['domain_sha256'],'task_source':b['task_source']})
 run=output/'native';command=build_command(run,b['run_id'],b['admission_id'],b['task_source'],mode='controlled_real')
 with (output/'host_native.log').open('xb') as log:proc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
 export_result(run,output,identity,proc.returncode)
 return proc.returncode
if __name__=='__main__':raise SystemExit(main())
