"""Same normal-owner entry for a reviewed subset of original failed reviewer requests."""
from pathlib import Path
import argparse,json,os,shutil,socket,subprocess,sys,time
import checkpoint_utils as U
S=U.S;P=U.P
def admission(path,review):
 m=U.read(path);a=U.read(review);assert m['fixture'] is False and path.resolve().is_relative_to(S/'packages')
 assert a['passed'] is True and a['approved_normal_admission_same_input_batch'] is True and a['manifest_sha256']==U.sha(path) and a['deployment_manifest_sha256']==U.sha(S/'deployment_manifest.json')
 assert a['physical_attempt_budget']==m['physical_attempt_budget'] and a['request_ids']==m['missing_request_ids'] and a['max_attempts_per_missing_request']==1 and a['minimum_failure_backoff_seconds']>=600
 assert a['bindings'] and all(U.sha(p)==h for p,h in a['bindings'].items());assert time.time()>=m['not_before_epoch'];return m
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--admission',type=Path);ap.add_argument('--fixture-output',type=Path);a=ap.parse_args();path=a.manifest.resolve();fake=None
 if a.fixture_output:
  m=U.read(path);assert m['fixture'] and path.is_relative_to((S/'fixtures').resolve());out=a.fixture_output.resolve();assert out.is_relative_to((S/'fixtures').resolve()) and not out.exists();shutil.copytree(m['original_snapshot'],out)
 else:
  assert a.admission;m=admission(path,a.admission);out=U.OUT;assert U.read(S/'fixtures/final_acceptance.json')['passed'] and U.read(S/'fixtures/namespace_acceptance.json')['passed']
 assert Path(m['output_dir'])==U.OUT
 for f,h in U.read(S/'deployment_manifest.json')['bindings'].items():assert U.sha(f)==h
 U.unchanged(out,Path(m['original_snapshot']),m['files']);sys.path.insert(0,str(P/'runtime'));import offline_exec
 readonly=[S,path.parent,P/'environments/cycleresearcher',P/'inputs/cycleresearcher_domains_n10_standard4_v2',P/'environments/cycleresearcher_revisions']+[Path(f) for f in U.read(S/'deployment_manifest.json')['bindings']]
 if a.fixture_output:readonly.append((S/'fixtures').resolve())
 command=[str(P/'environments/cycleresearcher/venv/bin/python'),'-B',str(S/'runner.py'),'--manifest',str(path)];socketpath='/tmp/insightpro-offline-model-20261117.sock'
 if a.fixture_output:
  command+=['--fixture-boundary'];socketpath=f'/tmp/cycle190-successor-fixture-{os.getpid()}.sock';fake=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);fake.bind(socketpath)
 argv=offline_exec.build_command(U.OUT if a.fixture_output else out,socketpath,command,[str(x) for x in readonly],'cycleresearcher')
 if a.fixture_output:
  targets=[i for i in range(len(argv)-2) if argv[i]=='--bind' and argv[i+1:i+3]==[str(U.OUT),str(U.OUT)]];assert len(targets)==1;argv[targets[0]+1]=str(out)
 (out/'offline_launch.json').write_text(json.dumps({'command':argv,'fixture':bool(a.fixture_output),'recovery_id':m['recovery_id']},indent=2)+'\n')
 try:return subprocess.run(argv).returncode
 finally:
  if fake:fake.close();Path(socketpath).unlink()
if __name__=='__main__':raise SystemExit(main())
