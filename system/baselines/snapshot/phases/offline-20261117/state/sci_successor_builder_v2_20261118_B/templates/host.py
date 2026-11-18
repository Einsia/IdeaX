from pathlib import Path
import argparse,hashlib,json,os,shutil,socket,subprocess,sys,time
S=Path(__file__).resolve().parent;P=S.parents[1];sys.path.insert(0,str(P/'runtime'));import offline_exec
read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--fixture-output',type=Path);a=ap.parse_args();manifest=a.manifest.resolve();m=read(manifest);pkg=manifest.parent;original=Path(m['output_dir']);out=a.fixture_output.resolve() if a.fixture_output else original
 for p,h in read(pkg/'source_bindings.json').items():assert sha(p)==h,p
 for r,h in m['files'].items():assert sha(Path(m['original_snapshot'])/r)==h,r
 if a.fixture_output:
  assert out.is_relative_to(S) and not out.exists();shutil.copytree(m['original_snapshot'],out,symlinks=True)
  if m['canonical_publication_required']:shutil.copyfile(pkg/'candidate_failure_result.json',out/'result.json')
 else:
  assert time.time()>=m['not_before_epoch'];accept=read(pkg/'fixture/transport_fixture_acceptance.json');assert accept['passed'] and all(accept['checks'].values()) and accept['model_calls']==0
  assert sha(out/'result.json')==m['expected_result_sha256']
  for r,h in m['files'].items():
   if r!='result.json':assert sha(out/r)==h,r
 method=m['method'];R=P/'environments/cycleresearcher_revisions';readonly=[S]
 if method=='cycleresearcher':
  python=P/'environments/cycleresearcher/venv/bin/python';runner=S/'cycle_runner.py';readonly += [P/'environments/cycleresearcher',P/'inputs/cycleresearcher_domains_n10_standard4_v2',R/'native-n10-standard4-selection-v2',R/'native-n10-standard4-bilingual-v3',R/'native-n10-standard4-source-spans-v4',P/'staging/cycleresearcher_chinese_review_diagnostic_v1',P/'staging/cycleresearcher_format_candidate_v4_20261117T1244/sealed_candidate_manifest.json']
 elif method=='researchagent':
  python=P/'environments/researchagent/venv/bin/python';runner=S/'ra_runner.py';route=read(m['route_path']);readonly += route['read_only']+[m['route_path'],P/'state/audit_researchagent_native_replay.py']
 elif method=='sciagents':
  python=P.parents[1]/'state/venv_sciagents/bin/python';runner=S/'sci_runner.py';graph=Path(m['graph_manifest']).parent;readonly += [graph,P/'inputs/sciagents_bge',P.parents[1]/'sources/sciagents-graphreasoning',P/'staging/sciagents_domain_graphs_v1/inputs/manifest.json']
 else:raise ValueError(method)
 command=[str(python),'-B',str(runner),'--manifest',str(manifest)];socketpath='/tmp/insightpro-offline-model-20261117.sock';fake=None
 if a.fixture_output:
  command+=['--fixture'];socketpath=f'/tmp/original-transport-fixture-{os.getpid()}.sock';fake=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);fake.bind(socketpath)
 argv=offline_exec.build_command(out,socketpath,command,[str(p) for p in readonly],method)
 if a.fixture_output:
  i=argv.index('--chdir');argv[i:i]=['--bind',str(out),str(original)]
 (out/'offline_launch.json').write_text(json.dumps({'command':argv,'fixture':bool(a.fixture_output),'recovery_id':m['recovery_id']},indent=2)+'\n')
 try:return subprocess.run(argv).returncode
 finally:
  if fake:fake.close();Path(socketpath).unlink()
if __name__=='__main__':raise SystemExit(main())
