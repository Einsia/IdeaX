"""Run the unmodified official ResearchAgent ideation/review/selection pipeline."""
from pathlib import Path
import argparse, copy, hashlib, json, sys, threading
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'sources/researchagent'
sys.path.insert(0,str(SOURCE/'code'))
from common import AstraClient, NativeFailure, InfrastructureFailure, read, save, now, single_prompt, safe

ENVIRONMENT = ROOT / 'environments/researchagent'
sys.path.insert(0, str(ENVIRONMENT))

class OfflineDependencyGap(InfrastructureFailure):
    pass


def prepare(domain, output_dir=None):
    from native_inputs import load_context
    try:
        context, evidence = load_context(domain['id'])
    except (FileNotFoundError, ValueError) as exc:
        raise OfflineDependencyGap(
            'ResearchAgent software and local SPECTER2 are ready, but verified native '
            'seed/reference inputs are unavailable or invalid for domain '
            + domain['id'] + ': ' + str(exc)
        ) from exc
    if output_dir is not None:
        save(Path(output_dir) / 'native_retrieval.json', evidence)
    return context

class NativeClient:
    def __init__(self,domain,out):
        self.client=AstraClient(out);self.domain=single_prompt(domain);self.counts={};self.lock=threading.Lock()
    def call(self,messages,max_retries=3):
        messages=copy.deepcopy(messages)
        messages.insert(1,{'role':'user','content':self.domain})
        digest=hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        with self.lock:
            occurrence=self.counts.get(digest,0)+1;self.counts[digest]=occurrence
        return self.client.chat(messages,max_tokens=32768,request_id='native-'+digest+'-'+str(occurrence)).strip()

def generate(domain,output_dir,client=None):
    from pipelines.research_pipeline import ResearchPipeline
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    from offline_support import require_offline
    require_offline(out,fresh_markers=('native_input.json','native_output.json','result.json'))
    context=prepare(domain,out);save(out/'native_input.json',context)
    pipeline=ResearchPipeline(api_client=client or NativeClient(domain,out),iterations=3)
    native=pipeline.run(copy.deepcopy(context));save(out/'native_output.json',native)
    missing=[k for k in ('problem','problem_rationale','method','method_rationale','experiment','experiment_rationale') if not native.get(k)]
    if missing:raise NativeFailure('Native ResearchAgent parser left required fields empty: '+', '.join(missing))
    sections=[('# Research problem',native['problem']),('## Problem rationale',native['problem_rationale']),('## Proposed method',native['method']),('## Method rationale',native['method_rationale']),('## Experiment design',native['experiment']),('## Experiment rationale',native['experiment_rationale'])]
    md='\n\n'.join(h+'\n\n'+v for h,v in sections)+'\n\n## Retrieved literature\n\n'+ '\n'.join('- '+r['title']+' — https://www.semanticscholar.org/paper/'+r['paperId'] for r in native['references'])+'\n'
    (out/'proposal.md').write_text(md)
    return {'status':'completed','proposal_markdown':md,'native_output_paths':[str(out/'native_output.json'),str(out/'native_input.json'),str(out/'native_retrieval.json'),str(out/'proposal.md')],'terminal_reason':None,'completed_at':now()}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--domain-json',required=True);ap.add_argument('--output-dir');ap.add_argument('--prepare-only',action='store_true');a=ap.parse_args();d=read(a.domain_json)
    if a.prepare_only:
        context=prepare(d);print(json.dumps({'domain':d['id'],'seed_title':context['paper']['title'],'references':len(context['references']),'entities':len(context['entities'])}));return
    out=Path(a.output_dir)
    try:result=generate(d,out)
    except OfflineDependencyGap as e:result={'status':'input_preparation_blocker','classification':'offline_dependency_gap','environment_ready':True,'benchmark_inputs_ready':False,'proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(e),'model_calls':0,'score':None}
    except InfrastructureFailure as e:result={'status':'infrastructure_failure','proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(e)}
    except NativeFailure as e:result={'status':'native_failure','proposal_markdown':None,'native_output_paths':[str(out/'native_output.json')],'terminal_reason':safe(e)}
    except Exception as e:result={'status':'adapter_failure','proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(e),'error_type':type(e).__name__}
    save(out/'result.json',result);print(json.dumps({'status':result['status'],'terminal_reason':result['terminal_reason']}))
if __name__=='__main__':main()
