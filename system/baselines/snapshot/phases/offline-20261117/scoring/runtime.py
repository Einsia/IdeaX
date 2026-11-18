"""Existing frozen Generation evidence/review and five-card Novelty protocol, Astra once."""
import argparse,hashlib,importlib.util,json,os,random,sys,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'adapters'));sys.path.insert(0,str(HERE/'vendor'))
from common import AstraClient,save,read,now,InfrastructureFailure,NativeFailure,safe
import evaluate as E
import api_shapes
import offline_evidence
from idea_benchmark import core
from idea_benchmark.panel import interesting_sequential as panel
from idea_benchmark.panel import sequential as seq
LITGRAPH='http://127.0.0.1:8766'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def direct_call(judge,prompt,packet,attempt):
    if judge!='astra':raise ValueError('Astra-only campaign')
    attempt.mkdir(parents=True,exist_ok=False)
    save(attempt/'binding.json',{'at':now(),'model':'gpt-6-astra','effort':'xhigh','prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'input_sha256':E.digest(packet)})
    response=AstraClient(attempt).completion([{'role':'system','content':prompt},{'role':'user','content':json.dumps(packet,ensure_ascii=False)}],request_id='judge',max_tokens=32768)
    text=response['choices'][0]['message'].get('content','');value=E.parse_json(text)
    save(attempt/'parsed.json',value)
    receipt={'judge':'astra','model':'gpt-6-astra','effort':'xhigh','native_session':response.get('id') or uuid.uuid4().hex,'usage':response.get('usage',{}),'parsed_sha256':sha(attempt/'parsed.json'),'transport':'OpenAI-compatible streaming, isolated message context'}
    save(attempt/'call_receipt.json',receipt);return value,receipt
E.model_call=direct_call
_original_read=E.read
def normalized_read(p):
    value=_original_read(p)
    return api_shapes.normalized(value) if Path(p).parent.name=='http' else value
E.read=normalized_read
E.evidence=lambda ident:offline_evidence.collect(E,ident)

def verify_sources():
    manifest=read(HERE/'source_manifest.json')
    for row in manifest['sources']:
        if sha(row['copy'])!=row['sha256']:raise ValueError('Frozen scoring source changed: '+row['copy'])
    if sha(HERE/'novelty_prompt.md')!=manifest['novelty_prompt_sha256']:raise ValueError('Novelty prompt changed')

def row_from_slot(slot):
    result=read(slot/'result.json',{})
    if result.get('status') not in ('success','completed'):raise ValueError('Unaccepted slot')
    text=result.get('proposal_markdown')
    if isinstance(text,str) and len(text)<4096:
        possible=Path(text)
        try:
            if possible.is_file():text=possible.read_text()
        except OSError:pass
    if not isinstance(text,str) or not text.strip():raise ValueError('No proposal text')
    method,domain,index=slot.parts[-3:];d=read(ROOT/'inputs'/domain/'domain.json')
    return {'system':method,'system_label':method,'task_id':domain,'idea_id':f'{method}-{domain}-{index}','domain':d['name'],'domain_ids':[x['id'] for x in d['litgraph_support']['subdomains']],'task_context':d['prompt'],'idea_text':text,'provided_reference_texts':[]}

def card(method,domain,index):
    verify_sources();slot=ROOT/'runs'/method/domain/f'slot-{index:02}';row=row_from_slot(slot)
    out=ROOT/'evaluations'/method/domain/f'slot-{index:02}';ident='idea_'+E.digest([method,domain,index])[:20]
    packet={'idea_id':ident,'domain_id':domain,'domain_ids':row['domain_ids'],'domain':row['domain'],'task_context':row['task_context'],'idea_text':row['idea_text'],'provided_reference_texts':[]}
    out.mkdir(parents=True,exist_ok=True)
    old=read(out/'inputs'/f'{ident}.json')
    if old is not None and old!=packet:raise ValueError('Frozen card changed')
    save(out/'inputs'/f'{ident}.json',packet)
    save(out/'manifest.json',{'raw_evidence_base_url':LITGRAPH,'evidence_protocol':offline_evidence.PROTOCOL,'protocol_id':'offline-common-corpus-20261117','source_result':str(slot/'result.json'),'source_sha256':sha(slot/'result.json'),'model':'gpt-6-astra','effort':'xhigh','repetitions':1,'mapping':{'C':'N','I':'I','S':'S'},'input_sha256':sha(out/'inputs'/f'{ident}.json')})
    (out/'score_prompt.md').write_text((HERE/'reviewer_prompt.md').read_text()+E.OUTPUT_CONTRACT)
    E.ROOT=out;E.MODELS={'astra':'gpt-6-astra'}
    E.evidence(ident);E.score(ident,'astra')
    assessment=read(out/'reviews'/ident/'astra/assessment.json')
    save(out/'result.json',{'status':'completed','at':now(),'method':method,'domain':domain,'slot':index,'C':assessment['N']['score'],'I':assessment['I']['score'],'S':assessment['S']['score'],'assessment_path':str(out/'reviews'/ident/'astra/assessment.json'),'proposal_sha256':hashlib.sha256(row['idea_text'].encode()).hexdigest()})

def novelty(method,domain):
    verify_sources();rows=[row_from_slot(ROOT/'runs'/method/domain/f'slot-{index:02}') for index in range(1,6)]
    out=ROOT/'evaluations'/method/domain/'novelty';out.mkdir(parents=True,exist_ok=True)
    seed=int(E.digest(['ar-baselines-full38-astra-20261116',method,domain,'novelty'])[:16],16);random.Random(seed).shuffle(rows)
    packets=[];mapping=[]
    for index,row in enumerate(rows,1):
        p=core.judge_packet(row,f'card_{index:02}');p['card_id']=p.pop('item_id');packets.append(p);mapping.append({'card_id':p['card_id'],'source_idea_id':row['idea_id']})
    data={'cards':packets,'mapping':mapping,'seed':seed,'mode':'per_system_five_proposals'}
    old=read(out/'input.json')
    if old is not None and old!=data:raise ValueError('Frozen panel changed')
    save(out/'input.json',data);cards={c['card_id']:c for c in packets};ids=list(cards);state=seq.initial_state()
    prompt=(HERE/'novelty_prompt.md').read_text();sessions=[]
    for n,kind in enumerate(('read','score'),1):
        stage={'stage_id':f'{n:02}-{kind}','kind':kind,'card_ids':ids};payload=seq.payload_for(stage,cards,state);dest=out/stage['stage_id'];dest.mkdir(exist_ok=True)
        value,receipt=E.cached_call(dest,'panel','astra',prompt,payload,lambda v:panel.validate_result(v,stage,cards,state))
        state=seq.advance(state,value,stage);save(dest/'assessment.json',value);save(dest/'receipt.json',receipt);sessions.append(receipt['native_session'])
    if set(state['ledger'])!=set(cards):raise ValueError('Incomplete Novelty panel')
    if len(set(sessions))!=len(sessions):raise ValueError('Reused judge session')
    scores={m['source_idea_id']:{'raw_100':state['ledger'][m['card_id']]['score'],'normalized_5':None if state['ledger'][m['card_id']]['score'] is None else state['ledger'][m['card_id']]['score']/20} for m in mapping}
    save(out/'assessment.json',state);save(out/'result.json',{'status':'completed','at':now(),'method':method,'domain':domain,'scores':scores,'repetitions':1,'model':'gpt-6-astra','input_sha256':sha(out/'input.json'),'prompt_sha256':sha(HERE/'novelty_prompt.md'),'sessions':sessions})

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['card','novelty','preflight']);p.add_argument('--method');p.add_argument('--domain');p.add_argument('--slot',type=int);a=p.parse_args()
    if a.stage=='preflight':verify_sources();print('Frozen evaluator import and source verification passed');return
    if os.environ.get('INSIGHTPRO_OFFLINE_ENFORCED')!='1':raise RuntimeError('Scoring requires common offline isolation launcher')
    try:
        if a.stage=='card':card(a.method,a.domain,a.slot)
        else:novelty(a.method,a.domain)
    except Exception as exc:
        dest=ROOT/'evaluations'/a.method/a.domain/(f'slot-{a.slot:02}' if a.stage=='card' else 'novelty')
        save(dest/'job_error.json',{'at':now(),'error_type':type(exc).__name__,'error':safe(exc),'status':'infrastructure_failure' if isinstance(exc,InfrastructureFailure) else 'evaluation_failure','stage':a.stage})
        raise
if __name__=='__main__':main()
