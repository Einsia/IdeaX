from pathlib import Path
import ast,json,re,hashlib
read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify_order(pkg,m):
 d=read(pkg/'object_order_diagnosis.json');r=m['resume_object_order_restoration'];assert d['restoration']==r and d['only_differing_field']=='/native_arguments/messages/0/content' and d['entire_difference_is_one_exact_original_draft_json_key_reordering']
 assert sha(r['source'])==r['sha256'];p=d['parser_source'];assert sha(p['path'])==p['sha256'];tree=ast.parse(Path(p['path']).read_text());names={'_repair_json_escapes','_first_json_start','_decode_escaping_stray_quotes','_scan_json','_extract_json'}
 nodes=[n for n in tree.body if (isinstance(n,ast.ImportFrom) and n.module=='__future__') or (isinstance(n,ast.FunctionDef) and n.name in names) or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'_JSON_ESCAPE_CHARS','_ESCAPE_PAIR_RE'} for t in n.targets))];scope={'json':json,'re':re};exec(compile(ast.Module(body=nodes,type_ignores=[]),p['path'],'exec'),scope);draft=scope['_extract_json'](read(r['source'])['text'])
 for key in r['parsed_value_path']:draft=draft[key]
 progress=read(sorted((Path(m['original_snapshot'])/'checkpoints').glob('*.json'))[-1])['native_progress']
 for path in r['progress_paths']:
  v=progress
  for key in path:v=v[key]
  assert json.dumps(v,ensure_ascii=False,sort_keys=True)==json.dumps(draft,ensure_ascii=False,sort_keys=True)
 mismatch=d['mismatch_evidence'];assert sha(mismatch['path'])==mismatch['sha256'];e=read(mismatch['path']);a=e['expected'];b=e['observed'];left=a['native_arguments']['messages'][0]['content'];right=b['native_arguments']['messages'][0]['content'];a['native_arguments']['messages'][0]['content']=right;assert a==b
 x=json.dumps(draft,ensure_ascii=False,indent=2);y=json.dumps(progress['debate']['draft'],ensure_ascii=False,indent=2)
 assert len([i for i in range(len(left)) if left.startswith(x,i) and left[:i]+y+left[i+len(x):]==right])==1
