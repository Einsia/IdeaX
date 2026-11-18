"""Original SciAgents automated 50-round graph-reasoning workflow, original graph."""
from pathlib import Path
import argparse,ast,json,os,sys,hashlib,random,heapq,pickle,types,time,re
from copy import deepcopy
from heapq import heappush,heappop
from datetime import datetime
from common import ROOT,AstraClient,NativeFailure,InfrastructureFailure,read,save,now,single_prompt,safe,MODEL
from offline_support import RawLibrary,require_offline,environment_text
class OfflineDependencyGap(InfrastructureFailure):pass

SOURCE=ROOT/'sources/sciagents';GRAPH_SOURCE=ROOT/'sources/sciagents-graphreasoning'

def load_functions(path,names,namespace):
    tree=ast.parse(path.read_text());selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    if len(selected)!=len(names):raise RuntimeError('Missing official functions: '+str(set(names)-{n.name for n in selected}))
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),namespace)

def setup(out):
    require_offline(out)
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import networkx as nx,numpy as np,torch,requests
    from scipy.spatial.distance import cosine
    from tqdm import tqdm
    from transformers import AutoTokenizer,AutoModel
    import autogen
    from openai.types.chat import ChatCompletion
    import autogen.oai.client as oai
    torch.set_num_threads(1)
    seed_path=out/'random_seed.json'
    seed_info=read(seed_path) or {'seed':int.from_bytes(os.urandom(8),'big')}
    save(seed_path,seed_info);random.seed(seed_info['seed']);np.random.seed(seed_info['seed']%(2**32));torch.manual_seed(seed_info['seed'])
    client=AstraClient(out);request_occurrences={}
    def create(self,params):
        messages=params['messages'];digest=hashlib.sha256(json.dumps(params,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
        request_occurrences[digest]=request_occurrences.get(digest,0)+1
        occurrence=request_occurrences[digest]
        request_id='native-'+digest+(f'-occurrence-{occurrence}' if occurrence>1 else '')
        raw=client.completion(messages,max_tokens=32768,request_id=request_id,tools=params.get('tools'),tool_choice=params.get('tool_choice'),response_format=params.get('response_format'))
        raw.setdefault('object','chat.completion')
        raw.setdefault('created',int(time.time()))
        raw.setdefault('id','native-'+digest)
        return ChatCompletion.model_validate(raw)
    oai.OpenAIClient.create=create
    namespace={'__name__':'sciagents_native','__file__':str(SOURCE/'ScienceDiscovery/agents.py'),'os':os,'nx':nx,'np':np,'torch':torch,'requests':requests,'random':random,'heapq':heapq,'pickle':pickle,'heappush':heappush,'heappop':heappop,'deepcopy':deepcopy,'datetime':datetime,'tqdm':tqdm,'cosine':cosine,'json':json,'time':time}
    load_functions(GRAPH_SOURCE/'GraphReasoning/graph_tools.py',['load_graph_with_text_as_JSON','load_embeddings','find_best_fitting_node_list','return_giant_component_of_graph'],namespace)
    load_functions(GRAPH_SOURCE/'GraphReasoning/graph_analysis.py',['euclidean_distance','heuristic_path_with_embeddings_with_randomization_waypoints','print_path_with_edges_as_list'],namespace)
    load_functions(SOURCE/'ScienceDiscovery/utils.py',['create_path'],namespace)
    graph_dir=ROOT/'inputs/sciagents_graph';model_dir=ROOT/'inputs/sciagents_bge'
    namespace['G']=nx.Graph(namespace['return_giant_component_of_graph'](namespace['load_graph_with_text_as_JSON'](data_dir=str(graph_dir),graph_name='large_graph_simple_giant.graphml')))
    namespace['node_embeddings']=namespace['load_embeddings'](graph_dir/'embeddings_simple_giant_ge-large-en-v1.5.pkl')
    namespace['embedding_tokenizer']=AutoTokenizer.from_pretrained(str(model_dir),local_files_only=True)
    namespace['embedding_model']=AutoModel.from_pretrained(str(model_dir),local_files_only=True)
    for name in ['gpt4o_config','gpt4o_config_graph','gpt4turbo_config','gpt4turbo_config_graph']:
        namespace[name]={'cache_seed':None,'config_list':[{'model':MODEL,'api_key':'transport-handled-by-common','base_url':'http://127.0.0.1:8765/v1'}],'timeout':540000}
    # Execute native agent definitions, prompts, tool registration and manager without importing visualization-only dependencies.
    tree=ast.parse((SOURCE/'ScienceDiscovery/agents.py').read_text())
    tree.body=[n for n in tree.body if not (isinstance(n,ast.ImportFrom) and (n.module or '').startswith('ScienceDiscovery.'))]
    exec(compile(tree,str(SOURCE/'ScienceDiscovery/agents.py'),'exec'),namespace)
    # Notebook human admin has no human answer available in a benchmark; leave native tool execution and termination intact.
    namespace['user'].human_input_mode='NEVER'
    from sciagents_offline_literature import bind_literature
    bind_literature(namespace,out)
    save(out/'native_config.json',{'system':'SciAgents','source_commit':'c5c30451b29cba813a11b5ce078909a214dad9f2','graphreasoning_commit':'f1d6d44a7d44123b7896029158ada9442c9dcc1a','model':MODEL,'reasoning_effort':'xhigh','native_max_round':50,'graph_repo':read(graph_dir/'repository.json'),'embedding_model_revision':read(model_dir/'revision.json'),'adaptations':['Common frozen raw-paper search and explicit local raw reader; native query function schema retained and source change disclosed','Fresh offline session; no online history/candidate reuse','Astra API transport','32768 completion cap includes reasoning instead of original 2048 visible-only cap','unattended UserProxyAgent human_input_mode NEVER','no AutoGen disk cache across independent benchmark slots','execute exact native graph function AST bodies to avoid unrelated visualization/import dependencies'],'domain_transfer_note':'Original bio-graph-1K retained; no fabricated ML-domain graph. Topic mismatch is a native transferred-workflow limitation.'})
    return namespace

def generate(domain,output_dir,client=None):
    out=Path(output_dir)
    require_offline(out,fresh_markers=('native_chat_history.json','native_partial_chat_history.json','result.json'))
    out.mkdir(parents=True,exist_ok=True)
    # Official graph.py loads the published graph and node embeddings directly.
    # A graph-to-fulltext manifest is not an upstream execution prerequisite.
    # Retain this fixed native prior and disclose its transfer/provenance limits;
    # independently retrieved papers still come only from the common raw corpus.
    save(out/'native_prior_disclosure.json',{
        'comparison_scope':'original-graph-transfer',
        'graph_role':'official_fixed_native_prior',
        'graph_source_fulltext_mapping_available':False,
        'graph_source_fulltext_mapping_required_by_official_generation':False,
        'matched_ml_graph_available':False,
        'common_raw_external_retrieval_only':True,
        'scoring_approved':False,
    })
    native=setup(out)
    try:
        from sciagents_offline_literature import sciagents_environment_text
        res=native['user'].initiate_chat(recipient=native['manager'],message=single_prompt(domain)+'\n\n'+sciagents_environment_text(),clear_history=True)
    finally:
        save(out/'native_partial_chat_history.json',native['groupchat'].messages)
        save(out/'native_novelty_chat_history.json',native['novelty_admin'].chat_messages.get(native['novelty_assistant'],[]))
    history=res.chat_history;save(out/'native_chat_history.json',history)
    return validate_output(out)

def validate_output(out):
    out=Path(out).resolve();history=read(out/'native_chat_history.json')
    if history is None:raise NativeFailure('No complete native SciAgents chat history saved')
    def render_message(m):
        text='## '+str(m.get('name',m.get('role','agent')))+'\n\n'+str(m.get('content') or '')
        if m.get('tool_calls'):text+='\n\n```json\n'+json.dumps(m['tool_calls'],ensure_ascii=False,indent=2)+'\n```'
        if m.get('tool_responses'):text+='\n\n```json\n'+json.dumps(m['tool_responses'],ensure_ascii=False,indent=2)+'\n```'
        return text
    text='\n\n'.join(render_message(m) for m in history)
    (out/'native_transcript.md').write_text(text+'\n')
    # Native paper output is the full expanded multi-agent document (automated notebook cell 7).
    scientists=[m for m in history if m.get('name')=='scientist' and m.get('content')]
    critics=[m for m in history if m.get('name')=='critic_agent' and m.get('content')]
    submitted_hypotheses=[]
    for m in history:
        for t in m.get('tool_calls') or []:
            f=t.get('function') or {}
            if f.get('name')=='rate_novelty_feasibility':
                try:
                    args=json.loads(f.get('arguments') or '{}')
                    if str(args.get('hypothesis') or '').strip():submitted_hypotheses.append(args['hypothesis'])
                except ValueError:pass
    save(out/'native_proposal_evidence.json',{'scientist_messages':len(scientists),'critic_messages':len(critics),'native_novelty_submitted_hypotheses':submitted_hypotheses,'note':'Native dynamic speaker choice is preserved; roles are not imposed as extra success gates.'})
    lit=[read(p) for p in (out/'literature_requests').glob('*.json')]
    literature_ok=any(isinstance(x.get('result'),dict) and bool(x['result'].get('data')) for x in lit)
    save(out/'literature_verification.json',{'successful_lookup':literature_ok,'successful_verification':None,'attempts':lit,'note':'Successful metadata retrieval does not establish completed novelty verification. Inspect the full native review and final message. Native tool failure handling is preserved; failed lookup alone does not invalidate an otherwise complete native proposal.'})
    if not scientists and not submitted_hypotheses:raise NativeFailure('Native SciAgents chat ended without any native proposal or submitted hypothesis')
    used_novelty=any('rate_novelty_feasibility' in json.dumps(m) for m in history)
    used_graph=any('generate_path' in json.dumps(m) for m in history)
    final=str(history[-1].get('content') or '') if history else ''
    withholding_patterns=[r'尚不足以交付',r'(?:无法|不能|尚不能|尚无法|暂不能|未能)[^。\n]{0,50}(?:交付|提交|提供|完成|形成)[^。\n]{0,50}(?:idea|提案|方案|想法)',r'(?:cannot|can\x27t|unable to|not yet able to)[^.\n]{0,80}(?:deliver|provide|complete|finalize|produce|formulate|submit)[^.\n]{0,80}(?:final|finished|complete|proposal|idea)',r'(?:need|require|awaiting)[^.\n]{0,80}(?:user|human)[^.\n]{0,80}(?:input|material|source|paper)',r'(?:请先|需要你|请用户)[^。\n]{0,80}(?:提供|补充|上传)[^。\n]{0,80}(?:原文|文献|论文|材料)']
    withholding=[m.group(0) for pattern in withholding_patterns for m in re.finditer(pattern,final,re.IGNORECASE)]
    literature_errors=[x for x in lit if isinstance(x.get('result'),str) and re.search(r'(?:status code\s*[45][0-9]{2}|timed?\s*out|connection\s*error|request failed)',x['result'],re.IGNORECASE)]
    literature_blocked=bool(withholding and literature_errors and re.search(r'文献|全文|论文|literature|paper|source',final,re.IGNORECASE))
    save(out/'native_terminal_assessment.json',{'explicit_final_withholding':bool(withholding),'matched_native_text':withholding,'literature_blocked':literature_blocked,'literature_errors':literature_errors,'native_final_message':final,'note':'Candidate hypotheses are not promoted to final output when the native terminal message explicitly withholds delivery or requires human input. No additional synthesis or candidate selection is performed.'})
    result={'status':'completed','proposal_markdown':None,'native_output_paths':[str(out/'native_chat_history.json'),str(out/'native_transcript.md')],'terminal_reason':None,'completed_at':now(),'qualification':'original bio-inspired graph transferred unchanged to supplied ML domain','output_kind':'full_native_conversation','literature_lookup_succeeded':literature_ok,'literature_verification_succeeded':None,'comparison_scope':'original-graph-transfer','native_graph_tool_requested':used_graph,'native_novelty_tool_requested':used_novelty,'native_hypothesis_submission_count':len(submitted_hypotheses),'native_speaker_roles':sorted({str(m.get('name',m.get('role'))) for m in history}),'native_history_messages':len(history),'native_groupchat_max_round':50,'native_final_message':final,'last_message_termination_marker':final.rstrip().endswith('TERMINATE'),'final_output_count':0 if withholding else 1}
    # The native notebook exports the full conversation, but a withheld deliverable remains provisional.
    proposal=text+'\n'
    if withholding:
        provisional=out/'provisional_native_output.md';provisional.write_text(proposal)
        result.update({'status':'infrastructure_failure' if literature_blocked else 'native_failure','terminal_reason':'Native terminal message explicitly withholds final proposal pending unavailable literature/human source input' if literature_blocked else 'Native terminal message explicitly withholds final proposal or requires human input','output_kind':'provisional_native_output','provisional_native_output':str(provisional),'literature_blocked':literature_blocked,'literature_verification_succeeded':False})
        result['native_output_paths'].append(str(provisional))
    else:
        (out/'proposal.md').write_text(proposal);result['proposal_markdown']=proposal;result['native_output_paths'].append(str(out/'proposal.md'))
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--domain-json',required=True);ap.add_argument('--output-dir',required=True);ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--validate-only',action='store_true');a=ap.parse_args();out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    if a.prepare_only:
        n=setup(out);print(json.dumps({'graph_nodes':len(n['G']),'graph_edges':n['G'].number_of_edges(),'agents':[x.name for x in n['groupchat'].agents]}));return
    try:result=validate_output(out) if a.validate_only else generate(read(a.domain_json),out)
    except OfflineDependencyGap as e:result={'status':'input_preparation_blocker','classification':'offline_dependency_gap_original_graph_transfer','proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(e),'model_calls':0,'score':None,'comparison_scope':'original-graph-transfer','scoring_approved':False}
    except InfrastructureFailure as e:result={'status':'infrastructure_failure','proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(e)}
    except NativeFailure as e:result={'status':'native_failure','proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(e)}
    except Exception as e:result={'status':'adapter_failure','proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(e),'error_type':type(e).__name__}
    save(out/'result.json',result);print(json.dumps({'status':result['status'],'terminal_reason':result['terminal_reason']}))
if __name__=='__main__':main()
