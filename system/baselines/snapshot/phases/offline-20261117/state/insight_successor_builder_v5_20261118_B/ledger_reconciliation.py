"""Exact historical storage-gap provenance and physical-index ledger reconciliation."""
from pathlib import Path
import hashlib,json,re
read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(value,message):
 if not value:raise RuntimeError(message)

def validated_storage(job,out,prior_path,prior):
 storage=(prior or {}).get('storage_interrupted_physical',{})
 if not storage:return {}
 require(prior_path is not None and prior['job_key']==job['key'] and prior['method']=='insightagents' and Path(prior['output_dir'])==out,'Inherited storage predecessor slot differs')
 rid=prior['recovery_id'];require(rid in job.get('executed_recovery_ids',[]),'Inherited storage predecessor was not executed');launches=[r for r in job.get('recovery_launches',[]) if r['recovery_id']==rid];require(len(launches)==1,'Inherited storage lacks a unique executed predecessor')
 command=launches[0]['command'];require('--manifest' in command and Path(command[command.index('--manifest')+1]).resolve()==prior_path.resolve(),'Inherited storage executed manifest differs')
 bindings=read(prior_path.parent/'source_bindings.json');require(bindings.get(str(prior_path))==sha(prior_path),'Inherited storage predecessor manifest source binding differs')
 for rel,proof in storage.items():
  require(bool(re.fullmatch(r'model_calls/[0-9a-f]{64}/physical-[0-9]{2,}',rel)),'Inherited storage path is not an exact physical directory')
  directory=out/rel;require(directory.resolve().is_relative_to(out.resolve()),'Inherited storage escapes original output')
  require(proof['classification']=='storage_interrupted_inflight_unknown' and proof['worker_identity_confirmed_exited'] and proof['raw_provider_terminal_absent'],'Inherited storage is not the reviewed condition')
  require(proof['actual_transport_end_at'] is None and proof['usage'] is None and proof['usd'] is None,'Inherited storage gap acquired an unsupported terminal or usage')
  require(not (directory/'receipt.json').exists() and not (directory/'error.json').exists() and {p.name:sha(p) for p in directory.iterdir() if p.is_file()}==proof['physical_files'],'Inherited storage interruption bytes differ')
  require(sha(directory/'request_body.json')==proof['stream_request_sha256'] and sha(directory/'native_sdk_request_body.json')==proof['native_request_sha256'],'Inherited storage original wire differs')
  starts=[e for e in proof['gateway_events'] if e['event']=='attempt_start'];require(len(starts)==1 and starts[0].get('mock') is False and starts[0]['request_sha256']==proof['stream_request_sha256'],'Inherited storage actual gateway start differs')
 return storage

def reconcile_storage_gaps(out,ledger,storage):
 missing=[]
 for rel,proof in storage.items():
  directory=out/rel;logical=str(directory.parent);index=int(directory.name.removeprefix('physical-'))
  starts=[e for e in ledger if e.get('event')=='attempt_start' and e.get('logical_call')==logical and e.get('physical_attempt')==index]
  terminals=[e for e in ledger if e.get('event') in ['attempt_end','attempt_error'] and e.get('logical_call')==logical and e.get('physical_attempt')==index]
  require(len(starts)==1 and not terminals,'Inherited storage must have exactly one original start and no local terminal')
  require(starts[0]['request_sha256']==proof['stream_request_sha256'] and starts[0]['native_sdk_request_sha256']==proof['native_request_sha256'],'Inherited storage ledger start wire differs')
  missing.append({'physical_directory':rel,'logical_call':logical,'physical_attempt':index,'start_at':starts[0]['at'],'usage':None,'usd':None})
 return missing

def reconcile_current_target(out,target,physical,ledger,storage_gaps):
 indices=[int(p.name.removeprefix('physical-')) for p in physical];require(indices==list(range(1,len(physical)+1)),'Current physical directories are not contiguous')
 starts=[e for e in ledger if e.get('event')=='attempt_start' and e.get('logical_call')==str(target)]
 ends=[e for e in ledger if e.get('event')=='attempt_end' and e.get('logical_call')==str(target)]
 start_ids=[e.get('physical_attempt') for e in starts];end_ids=[e.get('physical_attempt') for e in ends]
 require(all(type(x) is int for x in start_ids+end_ids),'Current physical ledger index is invalid')
 require(len(start_ids)==len(set(start_ids)) and set(start_ids)==set(indices),'Current target starts do not match every original physical exactly once')
 require(len(end_ids)==len(set(end_ids)),'Current target has duplicate physical ends')
 allowed={r['physical_attempt'] for r in storage_gaps if r['logical_call']==str(target)}
 require(set(end_ids)==set(indices)-allowed,'Current target ends differ outside the exact inherited storage gaps')
 for p in physical:
  index=int(p.name.removeprefix('physical-'));start=next(e for e in starts if e['physical_attempt']==index)
  require(start['request_sha256']==sha(p/'request_body.json') and start['native_sdk_request_sha256']==sha(p/'native_sdk_request_body.json'),'Current physical start wire differs')
  if index not in allowed:
   end=next(e for e in ends if e['physical_attempt']==index)
   require(end['request_sha256']==start['request_sha256'],'Current physical end wire differs')
 require(indices[-1] not in allowed,'Newest current failure still lacks a reviewed transport end')
 latest=next(e for e in ends if e['physical_attempt']==indices[-1])
 return latest,{'physical_attempts':len(indices),'completed_local_end_records':len(ends),'exact_inherited_storage_gap_indices':sorted(allowed),'latest_physical_has_actual_end':True}
