"""Separate prepared-domain-graph input variant; native agents and tools unchanged."""
import argparse
import hashlib
import json
from pathlib import Path
import types
import contextlib
import socket

import sciagents as native_adapter
from common import ROOT, read, save, now, single_prompt, NativeFailure, InfrastructureFailure, safe
from offline_support import require_offline
from sciagents_offline_literature import sciagents_environment_text


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def setup(output, graph_bundle, allow_pilot=False):
    output=require_offline(output);bundle=Path(graph_bundle).resolve()
    receipt=read(bundle/'acceptance.json',{})
    if not receipt.get('passed') or (receipt.get('pilot') and not allow_pilot):
        raise InfrastructureFailure('Matched graph input has not passed preparation acceptance')
    for file,key in [('large_graph_simple_giant.graphml','graph_sha256'),('embeddings_simple_giant_ge-large-en-v1.5.pkl','embedding_sha256')]:
        if digest(bundle/file)!=receipt.get(key):raise InfrastructureFailure('Prepared graph digest mismatch')
    view=output/'native_input_view';(view/'inputs').mkdir(parents=True,exist_ok=True)
    for name,target in [('sciagents_graph',bundle),('sciagents_bge',ROOT/'inputs/sciagents_bge')]:
        link=view/'inputs'/name
        if not link.exists():link.symlink_to(target,target_is_directory=True)
        if link.resolve()!=target.resolve():raise InfrastructureFailure('Native graph mount mismatch')
    # The existing setup function's code is unchanged. Only its input-root binding
    # points at this task's readonly graph and the same frozen BGE model.
    environment=dict(native_adapter.setup.__globals__,ROOT=view)
    setup_fn=types.FunctionType(native_adapter.setup.__code__,environment,'setup')
    native=setup_fn(output)
    config=read(output/'native_config.json')
    config.update(comparison_scope='matched-domain-abstract-graph',
        domain_transfer_note='Graph derived from this domain frozen raw original abstracts with upstream GraphReasoning. This variant is separate from the published bio-graph transfer.',
        graph_bundle=str(bundle),graph_input_acceptance=receipt,
        native_setup_source_sha256=digest(Path(native_adapter.__file__)))
    save(output/'native_config.json',config)
    save(output/'native_prior_disclosure.json',{
        'comparison_scope':'matched-domain-abstract-graph','matched_ml_graph_available':True,
        'graph_role':'prepared_native_prior_from_common_original_abstracts',
        'full_text_graph_claimed':False,'old_online_history_used':False,
        'graph_sha256':receipt['graph_sha256'],'input_version':'sciagents-common-raw-abstract-graphs-v1',
        'native_graph_input_receipt':receipt,'scoring_approved':False})
    return native


def verify(output,bundle,allow_pilot):
    checks={};calls=[]
    def forbid(*args,**kwargs):calls.append(1);raise RuntimeError('No model calls allowed in input preflight')
    native_adapter.AstraClient.completion=forbid
    try:socket.create_connection(('1.1.1.1',443),timeout=1).close();checks['public_network_denied']=False
    except OSError:checks['public_network_denied']=True
    with (output/'native_tools.log').open('w') as log,contextlib.redirect_stdout(log):
        native=setup(output,bundle,allow_pilot)
        graph=native['G'];vectors=native['node_embeddings']
        checks['input_graph_connected']=native['nx'].is_connected(graph)
        checks['embedding_coverage']=set(graph)<=set(vectors) and all(v.size==1024 for v in vectors.values())
        checks['native_dynamic_group']=len(native['groupchat'].agents)==13 and native['groupchat'].max_round==50 and native['groupchat'].speaker_selection_method=='auto'
        checks['fresh_context']=not native['groupchat'].messages
        left,right=sorted(graph.edges())[0]
        ok,response=native['user'].execute_function({'name':'generate_path','arguments':json.dumps({'keyword_1':left,'keyword_2':right})})
        text=response.get('content','');checks['native_graph_path_dispatch']=ok and ' -- ' in text and not text.startswith('Error')
        save(output/'native_graph_tool_response.json',response)
        ok,response=native['novelty_admin'].execute_function({'name':'response_to_query','arguments':json.dumps({'query':'language+model+memory'})})
        checks['native_local_literature_dispatch']=ok and 'common_frozen_raw_corpus' in response.get('content','')
    checks['zero_paid_calls']=not calls
    result={'at':now(),'passed':all(checks.values()),'checks':checks,'graph_bundle':str(bundle),
        'graph_acceptance_sha256':digest(Path(bundle)/'acceptance.json'),'comparison_scope':'matched-domain-abstract-graph',
        'pilot':allow_pilot,'benchmark_accepted':False,'model_calls':0}
    save(output/'acceptance.json',result);return result


def generate(domain,output,bundle):
    require_offline(output,fresh_markers=('native_chat_history.json','native_partial_chat_history.json','result.json'))
    acceptance=read(Path(bundle)/'native_path_acceptance.json',{})
    if not acceptance.get('passed') or acceptance.get('pilot'):
        raise InfrastructureFailure('Complete domain graph requires an accepted native path preflight')
    if acceptance.get('graph_acceptance_sha256')!=digest(Path(bundle)/'acceptance.json'):
        raise InfrastructureFailure('Native path acceptance is not bound to this graph')
    if read(Path(bundle)/'acceptance.json').get('domain_id')!=domain['id']:
        raise InfrastructureFailure('Graph domain mismatch')
    native=setup(output,bundle)
    environment=sciagents_environment_text().replace('The published graph is fixed native prior knowledge and is separate from retrieved raw literature.',
        'The graph is fixed native prior knowledge prepared with the upstream graph extractor from this domain original abstracts in the common raw corpus. Full text was not used to build this graph. It is separate from retrieved raw literature.')
    try:
        result=native['user'].initiate_chat(recipient=native['manager'],message=single_prompt(domain)+'\n\n'+environment,clear_history=True)
    finally:
        save(output/'native_partial_chat_history.json',native['groupchat'].messages)
        save(output/'native_novelty_chat_history.json',native['novelty_admin'].chat_messages.get(native['novelty_assistant'],[]))
    save(output/'native_chat_history.json',result.chat_history)
    final=native_adapter.validate_output(output)
    final.update(comparison_scope='matched-domain-abstract-graph',
        qualification='Official native SciAgents workflow with domain graph prepared from common raw original abstracts; separate from published bio-graph transfer.',
        graph_input_acceptance=read(Path(bundle)/'acceptance.json'))
    return final


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,required=True);ap.add_argument('--graph-bundle',type=Path,required=True)
    ap.add_argument('--domain-json',type=Path);ap.add_argument('--verify-only',action='store_true');ap.add_argument('--allow-pilot',action='store_true');args=ap.parse_args()
    out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    if args.allow_pilot and not args.verify_only:raise SystemExit('Pilot graphs are not proposal-generation inputs')
    if args.verify_only:
        result=verify(out,args.graph_bundle,args.allow_pilot);print(json.dumps(result));return 0 if result['passed'] else 2
    try:result=generate(read(args.domain_json),out,args.graph_bundle)
    except InfrastructureFailure as exc:result={'status':'infrastructure_failure','terminal_reason':safe(exc),'comparison_scope':'matched-domain-abstract-graph'}
    except NativeFailure as exc:result={'status':'native_failure','terminal_reason':safe(exc),'comparison_scope':'matched-domain-abstract-graph'}
    save(out/'result.json',result);print(json.dumps({'status':result['status'],'terminal_reason':result.get('terminal_reason')}));return 0


if __name__=='__main__':raise SystemExit(main())
