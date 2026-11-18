"""Exact original-slot admission; later slots require this domain's real terminal."""
import json, os
from pathlib import Path
from evidence import sha
ROOT=Path(__file__).resolve().parent;PHASE=ROOT.parents[1]
SCOPE='official-recommendation-graph-local-common-corpus-retrieval-adaptation'
def require(v,m):
    if not v:raise RuntimeError(m)
def bound(reference):
    p=Path(reference['path']);require(sha(p)==reference['sha256'],'Evidence SHA differs');return json.loads(p.read_text())
def verify_domain_acceptance(reference,domain,full=True):
    proof=bound(reference);result_path=PHASE/'runs/insightagents'/domain/'slot-01/result.json'
    require(proof.get('passed') is True and proof.get('fixture') is False and proof.get('method')=='insightagents' and proof.get('domain')==domain and proof.get('comparison_scope')==SCOPE,'Domain terminal identity differs')
    require(proof.get('checks') and all(v is True for v in proof['checks'].values()),'Domain native review not accepted')
    require(proof.get('bindings'),'Domain terminal evidence missing')
    if full:require(all(sha(p)==h for p,h in proof['bindings'].items()),'Domain terminal evidence changed')
    require(proof['bindings'].get(str(result_path))==sha(result_path),'Domain first result not bound')
    result=json.loads(result_path.read_text());require(result.get('status')=='completed' and result.get('proposal_markdown') and result.get('comparison_scope')==SCOPE,'Domain first native proposal not accepted')
    return proof
def verify_admission(path,expected_sha,manifest_path,output,domain,slot,model_socket=None):
    require(path and expected_sha,'Exact coordinator receipt required')
    receipt=bound({'path':str(path),'sha256':expected_sha});manifest=json.loads(Path(manifest_path).read_text())
    require(domain in manifest['topic_mapping']['domains'] and slot in [f'slot-{i:02}' for i in range(1,6)],'Unknown frozen domain or original slot')
    target=PHASE/'runs/insightagents'/domain/slot;topic=manifest['topic_mapping']['domains'][domain]
    expected={'schema':'insightagents-original-slot-admission-v2','enabled':True,'method':'insightagents','domain':domain,'slot':slot,'output':str(target),'comparison_scope':SCOPE,'fixture':False,'purpose':'original-native-generation','manifest_sha256':sha(manifest_path),'source_commit':manifest['source_commit'],'model':'gpt-6-astra','reasoning_effort':'xhigh','api':'responses','corpus_sha256':manifest['corpus_sha256'],'topic_sha256':topic['topic_sha256'],'scoring_gate_open':False,'automatic_followup_slots':False,'native_budget_and_retry_changes':False,'new_context':True}
    require(all(receipt.get(k)==v for k,v in expected.items()),'Receipt does not bind this exact original slot')
    require(Path(output).resolve()==target,'Output differs from exact slot')
    require(not (domain=='agent-memory' and slot=='slot-01'),'Accepted first original slot may never be sampled again')
    require(all(isinstance(receipt.get(k),str) and receipt[k].strip() for k in ['run_id','admission_id','model_socket']),'Missing explicit run/admission/socket identity')
    require(receipt['model_socket']=='/tmp/insightpro-offline-model-20261117.sock','Only shared physical250 bridge allowed')
    if model_socket is not None:require(str(Path(model_socket).resolve())==receipt['model_socket'],'Model socket differs')
    review=bound(receipt['independent_review'])
    require(review.get('status')=='accepted_staging_package' and review.get('manifest_sha256')==sha(manifest_path) and review.get('reviewer') and review.get('paid_calls')==0 and review.get('passed') is True,'Exact package needs independent acceptance')
    if slot!='slot-01':verify_domain_acceptance(receipt['domain_terminal_acceptance'],domain,full=os.environ.get('INSIGHTPRO_OFFLINE_ENFORCED')!='1')
    else:require(receipt.get('domain_terminal_acceptance') is None,'First-slot admission must not borrow another terminal')
    return receipt
