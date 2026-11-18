"""Route accepted old slots unchanged and new prepared domains to own slot01."""
from pathlib import Path
import argparse,json,subprocess,sys
from binding import ROOT,P,select,validate_output,verify_release,verify_bindings,read,require
sys.path.insert(0,str(P/'runtime'))
import offline_exec


def route(domain_json,output,*,fixture=False,model_socket=None):
 domain_path=Path(domain_json).resolve();domain_id=read(domain_path).get('id')
 routes=read(ROOT/'routes.json')
 require(domain_path==P/'inputs'/domain_id/'domain.json','Canonical original domain required')
 if domain_id not in routes['domains']:
  require(not fixture and model_socket is None,'Previous production routes cannot be used as fixtures')
  previous=routes['previous_route'];verify_bindings(previous['bindings'])
  return previous['command']+['--domain-json',str(domain_path),'--output-dir',str(Path(output).resolve())]
 domain,manifest_path,m,passthrough=select(domain_json)
 output=validate_output(output,m,fixture)
 require(not output.exists(),'Fresh independent first-slot output required')
 if not fixture:verify_release()
 verify_bindings(read(Path(manifest_path).parent/'graph_lineage.json')['bindings'])
 socket=read(ROOT/'routes.json')['shared_model_socket']
 if fixture:
  require(model_socket and str(Path(model_socket).resolve())!=socket,'Fixture requires a separate fake model socket')
  socket=str(Path(model_socket).resolve())
 else:require(model_socket is None,'Production shared model socket cannot be overridden')
 output.mkdir(parents=True)
 command=[str(P.parents[1]/'state/venv_sciagents/bin/python'),str(ROOT/'driver.py'),'--domain-json',str(domain_json),'--output-dir',str(output)]
 if fixture:command.append('--fixture')
 argv=offline_exec.build_command(output,socket,command,
   [str(Path(manifest_path).parent),str(ROOT),str(P/'inputs/sciagents_bge'),str(P.parents[1]/'sources/sciagents-graphreasoning'),
    str(P/'staging/sciagents_domain_graphs_v1/inputs/manifest.json')],'sciagents')
 (output/'offline_launch.json').write_text(json.dumps({'command':argv,'fixture':fixture,'comparison_scope':m['comparison_scope'],'domain':domain},indent=2)+'\n')
 return argv


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--domain-json',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True)
 ap.add_argument('--fixture',action='store_true');ap.add_argument('--model-socket');a=ap.parse_args()
 return subprocess.run(route(a.domain_json,a.output_dir,fixture=a.fixture,model_socket=a.model_socket)).returncode
if __name__=='__main__':raise SystemExit(main())
