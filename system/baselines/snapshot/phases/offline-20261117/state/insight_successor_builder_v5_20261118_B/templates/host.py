from pathlib import Path
import argparse,hashlib,json,os,shutil,socket,subprocess,sys,time
S=Path(__file__).resolve().parent;P=S.parents[1];R=P/'staging/insightagents_domain_admission_candidate_v2_20261118T0045'
sys.path.insert(0,str(R));import launcher,dispatch
read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--fixture-output',type=Path);a=ap.parse_args();m=read(a.manifest);original=Path(m['output_dir']);pkg=a.manifest.parent
 for p,h in read(pkg/'source_bindings.json').items():assert sha(p)==h,p
 c=dispatch.verify(m['host_contract']['path'],m['host_contract']['sha256'],read(m['host_contract']['path'])['domain_json'],original)
 for rel,h in m['files'].items():assert sha(Path(m['original_snapshot'])/rel)==h
 out=a.fixture_output.resolve() if a.fixture_output else original;fake=None;fakepath=None
 if a.fixture_output:
  assert out.is_relative_to(S) and not out.exists();shutil.copytree(m['original_snapshot'],out);shutil.copyfile(pkg/'candidate_failure_result.json',out/'result.json')
  fakepath=f'/tmp/insight-recovery-fixture-{os.getpid()}.sock';fake=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);fake.bind(fakepath)
 else:
  assert time.time()>=m['not_before_epoch'];receipt=read(pkg/'fixture/transport_fixture_acceptance.json');assert receipt['passed'] and all(receipt['checks'].values()) and receipt['model_calls']==0
  assert sha(out/'result.json')==m['expected_result_sha256']
  for rel,h in m['files'].items():
   if rel!='result.json':assert sha(out/rel)==h,rel
 argv=launcher.build(original,c['model_socket'],c['manifest']['path'],m['domain'],m['slot'],resume=True,admission_receipt=c['admission']['path'],admission_sha256=c['admission']['sha256'])
 command_index=max(i for i,value in enumerate(argv) if value==str(R/'adapter.py'));argv[command_index:]=[str(S/'driver.py'),'--manifest',str(a.manifest.resolve())]
 if a.fixture_output:argv.append('--fixture')
 i=argv.index('--chdir');argv[i:i]=['--ro-bind',str(S),str(S),'--ro-bind',m['host_contract']['path'],m['host_contract']['path']]
 if a.fixture_output:
  for i in range(len(argv)-2):
   if argv[i:i+3]==['--bind',str(original),str(original)]:argv[i+1]=str(out)
   if argv[i:i+3]==['--ro-bind',c['model_socket'],'/model.sock']:argv[i+1]=fakepath
 (out/'offline_launch.json').write_text(json.dumps({'command':argv,'fixture':bool(a.fixture_output),'recovery_id':m['recovery_id']},indent=2)+'\n')
 try:return subprocess.run(argv).returncode
 finally:
  if fake:fake.close();Path(fakepath).unlink()
if __name__=='__main__':raise SystemExit(main())
