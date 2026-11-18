"""Actual offline namespaces and native workflows; synthetic provider bytes only."""
from pathlib import Path
import argparse,collections,json,os,socket,subprocess
from evidence import sha,freeze
from launcher import build
ROOT=Path(__file__).resolve().parent
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--domain');a=ap.parse_args();out=Path(a.output).resolve();out.mkdir(exist_ok=False)
    mpath=ROOT/'sealed_manifest.json';m=json.loads(mpath.read_text());domains=[a.domain] if a.domain else list(m['topic_mapping']['domains'])
    sockpath=Path('/tmp')/f'insight-38domain-fixture-{os.getpid()}.sock';server=socket.socket(socket.AF_UNIX);server.bind(str(sockpath));server.listen(4);server.settimeout(0.01)
    rows=[]
    try:
        for domain in domains:
            target=out/domain;target.mkdir();command=build(target,sockpath,mpath,domain,'slot-01',fixture=True)
            freeze(out/(domain+'.launch.json'),{'argv':command,'fake_socket':str(sockpath),'fixture':True})
            with (out/(domain+'.log')).open('xb') as log:status=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
            try:conn,_=server.accept()
            except TimeoutError:connections=0
            else:conn.close();connections=1
            read=lambda name:json.loads((target/name).read_text()) if (target/name).exists() else {}
            boundary=read('offline_boundary.json');terminal=read('terminal.json');result=read('result.json');binding=read('run_binding.json');native=read('native_result.json')
            requests=[json.loads(p.read_text()) for p in target.glob('model_calls/*/request.json')];counts=collections.Counter(r['identity']['stage'] for r in requests)
            checks={'actual_offline_native_process_succeeded':status==0,'separate_network_namespace_no_default_route':boundary.get('no_default_route') is True and boundary.get('network_namespace')!=boundary.get('parent_network_namespace'),'no_gateway_connections':connections==0,'fixture_output_never_formal':result.get('status')=='fixture_completed' and terminal.get('formal_comparison_eligible') is False,'native_original_full_proposal_valid':terminal.get('native_proposal_valid') is True,'exact_domain_topic_bound':binding.get('domain')==domain and native.get('topic')==m['topic_mapping']['domains'][domain]['topic'],'full_native_debate_stages':sum(v for k,v in counts.items() if k.startswith('stage'))==22,'native_three_ballots_preserved':counts['stage1_endorsement.vote']==3,'all_requests_fixture_and_same_context':bool(requests) and all(r['scope_context']['fixture'] is True and r['run_binding_sha256']==sha(target/'run_binding.json') for r in requests),'shared_real_socket_never_mounted':'/tmp/insightpro-offline-model-20261117.sock' not in command}
            rows.append({'domain':domain,'passed':all(checks.values()),'checks':checks,'worker_exit':status,'logical_calls':len(requests),'native_stage_counts':dict(counts),'output':str(target)})
            freeze(out/(domain+'.acceptance.json'),rows[-1]);print(json.dumps(rows[-1]),flush=True)
        freeze(out/'acceptance.json',{'passed':all(r['passed'] for r in rows),'fixture':True,'domains':rows,'real_model_calls':0,'external_network_calls':0,'manifest_sha256':sha(mpath),'all_fixture_outputs_excluded_from_scoring':True})
    finally:server.close();sockpath.unlink()
if __name__=='__main__':main()
