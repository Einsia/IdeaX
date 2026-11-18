"""Only original unstarted slots; v4 source-span parser and native algorithm unchanged."""
from pathlib import Path
import argparse,json,hashlib,sys,subprocess
D=Path(__file__).resolve().parent;P=D.parents[2]
sys.path.insert(0,str(P/'runtime'));from offline_exec import build_command
SOCKET='/tmp/insightpro-offline-model-20261117.sock'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def build(domain_json,output,fixture_socket=None):
 manifest=json.loads((D/'manifest.json').read_text())
 for path,digest in manifest['sha256'].items():assert sha(path)==digest,path
 domain_json=Path(domain_json).resolve();output=Path(output).resolve();domain=json.loads(domain_json.read_text())['id']
 assert domain_json==P/'inputs'/domain/'domain.json'
 if fixture_socket:
  assert output.is_relative_to(P/'state') and str(Path(fixture_socket).resolve())!=SOCKET
  socket=str(Path(fixture_socket).resolve())
 else:
  rows=json.loads((D/'fresh_slots.json').read_text())['slots']
  assert sum(r['domain']==domain and r['output']==str(output) for r in rows)==1,'Only the162 original unstarted slots are authorized'
  socket=SOCKET
 assert not output.exists(),'Existing slot cannot be adopted or regenerated'
 command=[str(P/'environments/cycleresearcher/venv/bin/python'),str(D/'adapter.py'),'--domain-json',str(domain_json),'--output-dir',str(output)]
 readonly=[D,P/'environments/cycleresearcher',P/'inputs/cycleresearcher_domains_n10_standard4_v2',D.parent/'native-n10-standard4-selection-v2',D.parent/'native-n10-standard4-bilingual-v3',P/'staging/cycleresearcher_chinese_review_diagnostic_v1',P/'staging/cycleresearcher_format_candidate_v4_20261117T1244/sealed_candidate_manifest.json']
 argv=build_command(output,socket,command,extra_readonly=readonly,method='cycleresearcher')
 (output/'offline_launch.json').write_text(json.dumps({'command':argv,'fixture':bool(fixture_socket),'revision':'strict_explicit_source_spans_candidate_v4'},indent=2)+'\n');return argv

def main():
 p=argparse.ArgumentParser();p.add_argument('--domain-json',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--fixture-model-socket');a=p.parse_args()
 return subprocess.run(build(a.domain_json,a.output_dir,a.fixture_model_socket)).returncode
if __name__=='__main__':raise SystemExit(main())
