"""Normal-owner full native continuation gated by a sealed plan and real service recovery."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,socket,subprocess,sys
S=Path(__file__).resolve().parent;P=S.parents[1]
read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def admission(manifest,review):
 m=read(manifest)
 assert Path(manifest).resolve().is_relative_to(S/'packages') and m['fixture'] is False,'Fixture cannot be admitted live'
 a=read(review)
 assert a['passed'] is True and a['approved_normal_admission_same_input_batch'] is True and a['verified_service_recovered'] is True
 assert a['manifest_sha256']==sha(manifest) and a['deployment_manifest_sha256']==sha(S/'deployment_manifest.json')
 assert a['physical_attempt_budget']==10 and a['max_attempts_per_missing_request']==1 and a['minimum_failure_backoff_seconds']>=600
 health=a['service_health'];assert health==m['canary_health'] and sha(health['path'])==health['sha256'];h=read(health['path'])
 assert h['success'] is True and h['passed'] is True and h.get('real_gateway_required') is True and h['new_physical_attempts']==1 and h['probe_done'] is True and h['reviewer_stage_entered'] is False
 assert a['bindings'] and all(sha(p)==v for p,v in a['bindings'].items())
 return m
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',required=True,type=Path);ap.add_argument('--admission',type=Path);ap.add_argument('--fixture-output',type=Path);args=ap.parse_args()
 manifest=args.manifest.resolve();fake=None
 if args.fixture_output:
  m=read(manifest);assert m['fixture'] is True and manifest.is_relative_to(S/'fixtures')
  out=args.fixture_output.resolve();assert out.is_relative_to(S/'fixtures') and not out.exists();shutil.copytree(m['original_snapshot'],out)
 else:
  assert args.admission;m=admission(manifest,args.admission);out=Path(m['output_dir'])
  assert read(S/'fixtures/acceptance.json')['passed'] and read(S/'fixtures/namespace_acceptance.json')['passed']
 for p,h in read(S/'deployment_manifest.json')['bindings'].items():assert sha(p)==h,p
 original=Path(m['output_dir']);assert original==P/'runs/cycleresearcher/ai-control-deception/slot-05'
 for r,h in m['files'].items():assert sha(out/r)==h,r
 sys.path.insert(0,str(P/'runtime'));import offline_exec
 readonly=[S,manifest.parent,P/'environments/cycleresearcher',P/'inputs/cycleresearcher_domains_n10_standard4_v2',P/'environments/cycleresearcher_revisions/native-n10-standard4-selection-v2',P/'environments/cycleresearcher_revisions/native-n10-standard4-bilingual-v3',P/'environments/cycleresearcher_revisions/native-n10-standard4-source-spans-v4']+[Path(p) for p in read(S/'deployment_manifest.json')['bindings']]
 command=[str(P/'environments/cycleresearcher/venv/bin/python'),'-B',str(S/'runner.py'),'--manifest',str(manifest)]
 socketpath='/tmp/insightpro-offline-model-20261117.sock'
 if args.fixture_output:
  command+=['--fixture-boundary'];socketpath=f'/tmp/cycle190-continuation-fixture-{os.getpid()}.sock';fake=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);fake.bind(socketpath)
 argv=offline_exec.build_command(out,socketpath,command,[str(p) for p in readonly],'cycleresearcher')
 if args.fixture_output:
  i=argv.index('--chdir');argv[i:i]=['--bind',str(out),str(original)]
 (out/'offline_launch.json').write_text(json.dumps({'command':argv,'fixture':bool(args.fixture_output),'selection_semantics_revision':m['selection_semantics_revision'],'recovery_id':m['recovery_id']},indent=2)+'\n')
 try:return subprocess.run(argv).returncode
 finally:
  if fake:fake.close();Path(socketpath).unlink()
if __name__=='__main__':raise SystemExit(main())
