from pathlib import Path
import copy,importlib.util,json,tempfile,hashlib,ast
S=Path(__file__).resolve().parent;P=S.parents[1]
sp=importlib.util.spec_from_file_location('reviewed_hook',S/'hook.py');H=importlib.util.module_from_spec(sp);sp.loader.exec_module(H)
checks={}
def chk(k,v):
 checks[k]=bool(v);assert v,k
with tempfile.TemporaryDirectory(prefix='successor-v2-guards-',dir=S) as td:
 root=Path(td);H.P=root;H.S=root/'state/hook';H.O=root/'state/owner';H.S.mkdir(parents=True);H.O.mkdir();out=root/'runs/insightagents/domain/slot-01';out.mkdir(parents=True)
 key='insightagents__domain__01__generation';job={'key':key,'kind':'generation','method':'insightagents','domain':'domain','slot':1,'status':'infrastructure_failure','launches':1,'started':'2026-11-18T00:00:00+00:00','command':['original']}
 chk('never_launched_no_builder',not H.first_attempt_evidence({**job,'launches':0},out)[0]);chk('foreign_output_no_builder',not H.first_attempt_evidence(job,root/'outside')[0])
 chk('no_request_no_builder',not H.first_attempt_evidence(job,out)[0]);q=out/'model_calls/q';q.mkdir(parents=True);(q/'request.json').write_text('{}')
 chk('zero_physical_no_builder',not H.first_attempt_evidence(job,out)[0]);physical=q/'physical-01';physical.mkdir();chk('missing_receipt_no_builder',not H.first_attempt_evidence(job,out)[0]);(physical/'receipt.json').write_text('{}');(out/'model_attempts.jsonl').write_text('{}\n')
 chk('first_real_evidence_delegates_strict_builder',H.first_attempt_evidence(job,out)[0]);(out/'terminal.json').write_text('{}');chk('native_terminal_no_API_retry',not H.first_attempt_evidence(job,out)[0]);(out/'terminal.json').unlink()
 m={'target_directory':'model_calls/q','prior_physical_attempts':1};chk('same_attempt_count_no_successor',not H.new_attempt_evidence(job,{},m,out,{})[0]);(q/'physical-02').mkdir();chk('new_physical_requires_strict_builder',H.new_attempt_evidence(job,{},m,out,{})[0])
 (q/'physical-02'/'receipt.json').write_text('{}')
 release=root/'release.json';release.write_text('{}');cfg={'enabled':True,'bindings':{},'allowed_keys':[key],'builders':{'insightagents':{'command':['fixture-builder'],'release':H.ref(release)}},'revision':'fixture'}
 for path,value in [(H.S/'configuration.json',cfg),(root/'state/campaign.json',{'jobs':{key:job}}),(root/'state/generation_recoveries.json',{}),(H.O/'reviewed_queue.json',{'batches':[]})]:H.C.save(path,value)
 H.C.alive=lambda h:False;H.C.result_path=lambda j:out/'result.json';calls=[]
 def launch(cmd,record,stage):
  calls.append((cmd,record,stage));record.update(stage=stage,process={'pid':1,'start':'fixture'});H.C.save(H.S/'active.json',record);return record
 H.launch=launch
 H.tick();chk('tick_handles_first_failure_without_registry',len(calls)==1 and calls[0][0][0]=='fixture-builder' and calls[0][1]['prior_launches']==1)
 H.C.save(H.S/'active.json',{});calls.clear();H.C.save(root/'state/generation_recoveries.json',{key:{'recovery_id':'not-executed'}});H.tick();chk('pending_approved_recovery_not_duplicated',not calls)
 H.C.save(root/'state/generation_recoveries.json',{});H.C.save(H.S/'waiting.json',{'other':{'signature':'other','not_before_epoch':H.time.time()+600}});H.tick();chk('other_slot_backoff_does_not_block_first_failure',len(calls)==1)
 H.C.save(H.S/'active.json',{});calls.clear();H.C.save(H.S/'waiting.json',{'due':{'signature':'due','method':'insightagents','handoff':str(root/'handoff'),'not_before_epoch':0}});H.review_command=lambda p,m:['fixture-review'];H.tick();chk('due_review_prioritized_once',len(calls)==1 and calls[0][0]==['fixture-review'] and not H.read(H.S/'waiting.json'))
 source=(P/'state/ar_baselines_normal_recovery_owner_20261118T0020/owner_v4_base.py').read_text();tree=ast.parse(source);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='process');guards=[n for n in ast.walk(fn) if isinstance(n,ast.Assert) and 'methods' in ast.unparse(n.test) or isinstance(n,ast.Assert) and 'request_concurrency' in ast.unparse(n.test)];code=compile(ast.fix_missing_locations(ast.Module(body=guards,type_ignores=[])),'capacity guards','exec')
 def capok(methodcap=230,gen=230,score=20,http=250):
  try:exec(code,{'methods':{x:{'max_generation_workers':methodcap} for x in ['sciagents','insightagents','cycleresearcher']},'ctl':{'generation_workers':gen,'scoring_workers':score,'request_concurrency':http}});return True
  except AssertionError:return False
 chk('method230_with_global230_HTTP250',capok());chk('method231_refused',not capok(methodcap=231));chk('global231_refused',not capok(gen=231));chk('scoring21_refused',not capok(score=21));chk('HTTP251_refused',not capok(http=251))
H.C.save(S/'guard_acceptance.json',{'at':H.C.now(),'passed':True,'checks':checks,'new_model_calls':0,'shared_mutations':False,'tested_hook_sha256':hashlib.sha256((S/'hook.py').read_bytes()).hexdigest()});print(json.dumps({'passed':True,'checks':len(checks),'model_calls':0}))
