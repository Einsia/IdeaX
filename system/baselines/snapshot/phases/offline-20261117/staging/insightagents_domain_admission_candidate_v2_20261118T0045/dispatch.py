"""Frozen slot dispatch; never registers, enables, retries, or replaces a run."""
from pathlib import Path
import argparse,json,os
from evidence import sha
from controlled_gate import verify_admission,require
ROOT=Path(__file__).resolve().parent;PHASE=ROOT.parents[1]
def verify(contract_path,digest,domain_json,output_dir,registration_path=None):
    require(sha(contract_path)==digest,'Host contract changed');c=json.loads(Path(contract_path).read_text())
    require(c.get('schema')=='insightagents-original-slot-host-v2' and c.get('fixture') is False,'Nonproduction host contract')
    require(Path(domain_json).resolve()==Path(c['domain_json']) and Path(output_dir).resolve()==Path(c['output']),'Invocation identity differs')
    require(all(sha(p)==h for p,h in c['bindings'].items()),'Host bindings changed')
    a=verify_admission(c['admission']['path'],c['admission']['sha256'],c['manifest']['path'],c['output'],c['domain'],c['slot'],c['model_socket'])
    require(sha(c['manifest']['path'])==c['manifest']['sha256'],'Package changed')
    manifest=json.loads(Path(c['manifest']['path']).read_text());require(all(sha(r['path'])==r['sha256'] for r in manifest['bound_files']),'Frozen runtime changed')
    reg=json.loads(Path(registration_path or PHASE/'state/new_method_accounting/registered.json').read_text())['registrations'];row=c['accounting_registration']
    require(reg.count(row)==1 and row['root']==c['output'] and all(row[k]==a[k] for k in ['run_id','admission_id','comparison_scope','method']),'Exact incremental costs must be registered before calls')
    command=[manifest['python_executable'],str(ROOT/'launcher.py'),'--output',c['output'],'--model-socket',c['model_socket'],'--manifest',c['manifest']['path'],'--domain',c['domain'],'--slot',c['slot'],'--admission-receipt',c['admission']['path'],'--admission-sha256',c['admission']['sha256']]
    require(command==c['command'],'Host command differs from exact package/slot');require(Path(c['model_socket']).is_socket(),'Shared bridge missing')
    return c
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--contracts',required=True);ap.add_argument('--domain-json',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args()
    d=json.loads(Path(a.domain_json).read_text())['id'];slot=Path(a.output_dir).name
    path=Path(a.contracts)/d/slot/'host_contract.json';index=json.loads((Path(a.contracts)/'index.json').read_text());key=d+'/'+slot
    require(key in index['contracts'],'Slot has no reviewed explicit host contract');require(index['contracts'][key]=={'path':str(path),'sha256':sha(path)},'Host index changed')
    c=verify(path,index['contracts'][key]['sha256'],a.domain_json,a.output_dir)
    require(not Path(c['output']).exists(),'Original slot already exists; no automatic new sample or retry')
    Path(c['output']).mkdir(parents=True,exist_ok=False)
    os.execv(c['command'][0],c['command'])
if __name__=='__main__':main()
