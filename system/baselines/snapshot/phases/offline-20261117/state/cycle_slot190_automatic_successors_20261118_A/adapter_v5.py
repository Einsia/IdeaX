"""Original Cycle generator/reviewer plus upstream parser and tutorial selection.

This module cannot construct a live transport. Callers must provide reviewed clients.
The target-only canary does not execute run_chain or construct a reviewer.
"""
from pathlib import Path
import ast,hashlib,importlib.util,json,sys
S=Path(__file__).resolve().parent;P=S.parents[1]
D=P/'environments/cycleresearcher_revisions/native-n10-standard4-source-spans-v4'
SOURCE=P.parents[1]/'sources/cycleresearcher'
REVISION='cycleresearcher-upstream-parser-tutorial-fallback-v5-20261118'
sys.path.insert(0,str(D))
spec=importlib.util.spec_from_file_location('preserved_cycle_v4_transport',D/'adapter.py')
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def payload(messages,max_tokens,kwargs):
 value={'model':'gpt-6-astra','messages':messages,'reasoning_effort':'xhigh','max_completion_tokens':max_tokens,'stream':True,'stream_options':{'include_usage':True}}
 for key in ['tools','tool_choice','response_format','stop','n','seed','parallel_tool_calls']:
  if kwargs.get(key) is not None:value[key]=kwargs[key]
 return value
def native_select(reviews):
 tree=ast.parse(''.join(read(SOURCE/'Tutorial/tutorial_3.ipynb')['cells'][13]['source']))
 fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='extract_average_rating')
 maximum=next(x for x in ast.walk(tree) if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='best_paper' for t in x.targets))
 scope={'np':V.np};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SOURCE/'Tutorial/tutorial_3.ipynb')+':cell13:rating','exec'),scope)
 ratings=[{'index':i,'avg_rating':float(scope['extract_average_rating'](review)),'decision':review.get('decision','No decision'),'reviewer_count':len(review.get('reviews',[])),'score_source':V.rating_source(review)} for i,review in enumerate(reviews)]
 scope['paper_ratings']=ratings;exec(compile(ast.Module(body=[maximum],type_ignores=[]),str(SOURCE/'Tutorial/tutorial_3.ipynb')+':cell13:max','exec'),scope)
 return scope['best_paper'],ratings
def researcher_plan(config):
 """Execute official generator to its original ten-request model boundary only."""
 captured=[]
 class Boundary(BaseException):pass
 class Model:
  def generate(self,prompts,sampling_params):
   assert len(prompts)==10
   for i,text in enumerate(prompts):captured.append({'component':'researcher','request_id':f'researcher-{i+1:04}','original_index':i,'payload':payload(json.loads(text),sampling_params.max_tokens,{'stop':sampling_params.stop or None})})
   raise Boundary()
 researcher=V.CycleResearcher.__new__(V.CycleResearcher);researcher.tokenizer=V.MessageTransport();researcher.model=Model()
 references=Path(config['references_file']).read_text();assert V.text_sha(references)==config['references_sha256']
 try:researcher.generate_paper(topic=config['topic'],references=references,max_tokens=19000,n=10)
 except Boundary:pass
 assert len(captured)==10;return captured
def run_chain(config,output,clients):
 """Actual full native chain; no compatibility mapping or additional score guard."""
 assert set(clients)=={'researcher','reviewer'}
 out=Path(output);legacy=V.material_record(config);V.frozen_json(out/'input_material_version.json',legacy)
 derived=read(S/'configuration_v5.json');assert config['domain_id']==derived['domain_id'] and sha(V.INPUTS/config['domain_id']/'configuration.json')==derived['original_configuration_sha256']
 material={**legacy,'configuration_id':derived['configuration_id'],'configuration_sha256':sha(S/'configuration_v5.json'),'configuration_path':str(S/'configuration_v5.json'),'deployment_manifest_sha256':sha(S/'deployment_manifest.json'),'deployment_manifest_path':str(S/'deployment_manifest.json'),'format_compatibility_revision':'legacy-carrier-only-upstream-review-parser-v5','selection_semantics_revision':REVISION,'missing_score_policy':'upstream_internal_zero_then_first_max','review_output_compatibility_used_for_selection':False,'original_configuration_sha256':legacy['configuration_sha256'],'original_deployment_manifest_sha256':legacy['deployment_manifest_sha256'],'original_format_compatibility_revision':legacy['format_compatibility_revision']}
 V.frozen_json(out/'input_material_version_v5_checkpoint.json',material)
 references=Path(config['references_file']).read_text();assert V.text_sha(references)==config['references_sha256']
 researcher=V.CycleResearcher.__new__(V.CycleResearcher);researcher.tokenizer=V.MessageTransport();researcher.model=V.ModelTransport(out,'researcher',clients['researcher'])
 reviewer=V.DeepReviewer.__new__(V.DeepReviewer);reviewer.tokenizer=V.MessageTransport();reviewer.model=V.ModelTransport(out,'reviewer',clients['reviewer'])
 papers=researcher.generate_paper(topic=config['topic'],references=references,max_tokens=19000,n=10);assert len(papers)==10
 V.frozen_json(out/'generated_papers.json',papers);carriers=[];mapping=[]
 for i,paper in enumerate(papers):
  carrier,detail=V.paper_carrier(paper);carriers.append(carrier)
  V.frozen_json(out/'candidates'/f'{i:02}.json',paper);V.frozen_text(out/'carriers'/f'{i:02}.txt',carrier)
  mapping.append({'original_index':i,'carrier_key':detail['carrier_key'],'carrier_sha256':V.text_sha(carrier),'generated_text_sha256':V.text_sha(paper['generated_text']),'native_latex_nonempty':detail['carrier_key']=='latex','format_compatibility':detail})
 V.frozen_json(out/'carrier_mapping.json',mapping)
 reviews=reviewer.evaluate(carriers,mode='Standard Mode',reviewer_num=4,max_tokens=35000)
 assert len(reviews)==10 and len(researcher.model.completed)==len(reviewer.model.completed)==10
 V.frozen_json(out/'native_reviews.json',reviews)
 for i,review in enumerate(reviews):V.frozen_json(out/'reviews'/f'{i:02}.json',review)
 best,ratings=native_select(reviews);index=best['index'];proposal=carriers[index]
 selection={'selected_original_index':index,'ratings':ratings,'tie_break':'first original index','score_scope':'internal_candidate_selection_only','selection_semantics_revision':REVISION,'missing_score_policy':'upstream_internal_zero_then_first_max','review_output_compatibility_used_for_selection':False,'completed_logical_responses':{'generation':10,'review':10},'selected_carrier':mapping[index]}
 V.frozen_json(out/'selection_v5.json',selection);V.frozen_text(out/'proposal_v5.md',proposal)
 return {**material,'status':'completed','proposal_markdown':proposal,'selected_original_index':index,'completed_logical_responses':20,'selection_semantics_revision':REVISION,'missing_score_policy':'upstream_internal_zero_then_first_max','review_output_compatibility_used_for_selection':False,'native_output_paths':[str(out/x) for x in ['input_material_version_v5_checkpoint.json','generated_papers.json','native_reviews.json','carrier_mapping.json','selection_v5.json','proposal_v5.md']],'canonical_publication_required':True}
