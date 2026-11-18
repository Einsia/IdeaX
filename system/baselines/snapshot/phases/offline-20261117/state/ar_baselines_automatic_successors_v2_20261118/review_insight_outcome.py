from pathlib import Path
import datetime,hashlib,importlib.util,json,sys
read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify_outcome(pkg,m,fm,release):
 out=Path(m['output_dir']);classification=read(pkg/'classification.json');target=out/m['target_directory'];physical=sorted(target.glob('physical-*'));latest=physical[-1];receipt=read(latest/'receipt.json');assert sha(latest/'response_body.bin')==receipt['response_sha256'] and sha(latest/'request_body.json')==receipt['request_sha256'];ledger=[json.loads(l) for l in (out/'model_attempts.jsonl').read_text().splitlines()];ends=[e for e in ledger if e['event']=='attempt_end'];storage=m.get('storage_interrupted_physical',{})
 if storage:
  previous=classification['original_recovery_manifest'];assert sha(previous['path'])==previous['sha256'];prior=read(previous['path']);assert prior['storage_interrupted_physical']==storage
  sys.path.insert(0,str(release.parent));spec=importlib.util.spec_from_file_location('strict_reviewed_ledger',release.parent/'ledger_reconciliation.py');L=importlib.util.module_from_spec(spec);spec.loader.exec_module(L);job=classification['original_job'];assert L.validated_storage(job,out,Path(previous['path']),prior)==storage;gaps=L.reconcile_storage_gaps(out,ledger,storage);actual,proof=L.reconcile_current_target(out,target,physical,ledger,gaps);assert actual==classification['latest_failure_end'] and len(gaps)==len(storage)
 else:gaps=[]
 assert fm['all_unknown_usage_attempts']==sum(e.get('usage') is None for e in ends)+len(gaps)
 if receipt.get('provider_status')=='failed':
  events=[]
  for frame in (latest/'response_body.bin').read_text().replace('\r\n','\n').split('\n\n'):
   data='\n'.join(l[5:].lstrip(' ') for l in frame.splitlines() if l.startswith('data:'))
   if data and data!='[DONE]':events.append(json.loads(data))
  spec=importlib.util.spec_from_file_location('strict_reviewed_provider_failure',release.parent/'provider_failure.py');F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F);failure=F.explicit_server_failure(receipt,events);assert failure==m['provider_failure_terminal']==fm['provider_failure_terminal']==classification['provider_failure_terminal'];delay=F.retry_delay_seconds(failure,classification['latest_failure_end']['at']);assert delay==m['provider_retry_after_seconds'] and m['not_before_epoch']>=datetime.datetime.fromisoformat(classification['latest_failure_end']['at']).timestamp()+max(600,delay)
 else:assert receipt.get('provider_status') is None and receipt.get('usage') is None
