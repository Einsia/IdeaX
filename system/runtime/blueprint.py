"""Native Astra writing with condition-specific access and frozen source cards."""
import re
import shutil
from common import *

SECTIONS=['标题与核心主张','为什么提出这个 idea：从 problem、insight 到设计','问题定义','方法的完整展开','一个具体例子','与最近前作的实质差异','初步验证方案','贡献、适用边界与开放问题','相对原卡的新增说明']
SUFFIXES={'.md','.txt','.json','.jsonl','.html','.htm','.csv','.xml'}
SECRET=re.compile(r'\bsk-[A-Za-z0-9_-]{12,}|(?i:authorization\s*[=:]\s*["\x27]?bearer\s+[^\s"\x27]+)')

def snapshot(source, target):
    if source.is_symlink(): raise ValueError('Symlinked source evidence rejected')
    target.parent.mkdir(parents=True,exist_ok=True)
    text=source.read_text(errors='replace');clean=SECRET.sub('[REDACTED_CREDENTIAL]',text)
    target.write_text(clean)
    return dict(source=str(source),source_sha256=sha(source),sha256=sha(target),redacted=clean!=text)

def prepare_domain(source_run, output, domain):
    from multi_source import validate_source
    source_run=Path(source_run); output=Path(output)
    if (output/'manifest.json').exists(): return read(output/'manifest.json')
    source=read(source_run/'evaluation_source.json');validate_source(source)
    accepted=read(source['acceptance_file']);cards=read(source['ideas'])
    if len(cards)!=5:raise ValueError('Five accepted source cards required')
    # A new domain is prepared atomically; an interruption can safely repeat it.
    temp=output.with_name(output.name+'.preparing')
    if temp.exists():shutil.rmtree(temp)
    temp.mkdir(parents=True)
    evidence=temp/'evidence';evidence.mkdir();index={};logs=[]
    if RELEASE['kind']=='multi':
        if not read(source_run/'completion_check.json')['ok']:raise ValueError('Multi phase barriers not complete')
        roots=[(a,source_run/'authors'/a/'work/out') for a in AUTHORS]
        for name in ('generation.json','discussions.json','responses.json','final_pool.json'):
            index['debate/'+name]=snapshot(source_run/name,evidence/'debate'/name)
        top1=dict(original_rank=1,policy='Existing selector rank 1, frozen before external review',files={})
    else:
        roots=[('single',source_run/'work/out')]
        top1=read(source_run/'selector_top1.json')
        verify(top1['files'])
    for label,folder in roots:
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.suffix.lower() not in SUFFIXES:continue
            key=label+'/'+str(path.relative_to(folder));index[key]=snapshot(path,evidence/key)
        logs.append('## '+label+'\n\n'+(folder/'SEARCH_LOG.md').read_text())
    (evidence/'SEARCH_LOG.md').write_text(SECRET.sub('[REDACTED_CREDENTIAL]','\n\n'.join(logs)))
    index['SEARCH_LOG.md']={'sha256':sha(evidence/'SEARCH_LOG.md'),'provenance':'Concatenation of actual saved per-author search logs'}
    if ACCESS=='full':
        # The release shares one hash-checked snapshot across both Full systems.
        path=(SYSTEM/'domains'/domain/'full_context.jsonl').resolve()
        index['full_domain_context.jsonl']=snapshot(path,evidence/'full_domain_context.jsonl')
    save(evidence/'index.json',index)
    task=read(SYSTEM/'domains'/domain/'task.json');items=[]
    for rank,card in enumerate(cards,1):
        selected=accepted['selected'][rank-1];original=Path(selected['path'])
        if sha(original)!=selected['sha256'] or read(original)!=card:raise ValueError('Selected card binding mismatch')
        ident=f'{domain}__{rank:02}';dest=temp/'inputs'/ident
        dest.mkdir(parents=True);shutil.copy2(original,dest/'original_idea.json')
        save(dest/'research_record.json',dict(schema='explicit-source-index-v1',source_domain=domain,
            original_sha256=sha(original),original_fields=card,source_index='evidence/index.json',
            provenance='Retrospective extraction of explicit saved outputs, not reconstructed private reasoning.',
            missing_records=['No invented historical rationale; unrecorded bridges must be labelled writing-stage additions.'],
            actual_access=ACCESS))
        items.append(dict(id=ident,domain=domain,name=task['name'],rank=rank,original_sha256=sha(original),
                          selector_top1=rank==top1['original_rank']))
    files={str(p.relative_to(temp)):sha(p) for folder in ('inputs','evidence') for p in (temp/folder).rglob('*') if p.is_file()}
    save(temp/'manifest.json',dict(created=now(),condition=CONDITION,access=ACCESS,items=items,files=files,
        source_run=str(source_run),source_acceptance=source['acceptance_file'],source_acceptance_sha256=source['acceptance_sha256'],
        selector=top1,model='gpt-6-astra',effort='xhigh',provider=PROVIDER,baseline_blueprints=False,
        prompt_sha256=sha(SYSTEM/'prompts/blueprint.md')))
    temp.rename(output);return read(output/'manifest.json')

def valid(root, item):
    receipt=read(root/'runs'/item['id']/'completion.json',{})
    if not receipt:return False
    try:
        verify(receipt['files'])
        return receipt['original_sha256']==item['original_sha256']
    except (OSError,ValueError):return False

def worker(root, ident):
    import single
    from multi import invoke
    root=Path(root);manifest=read(root/'manifest.json');item=next(x for x in manifest['items'] if x['id']==ident)
    if valid(root,item):return
    if manifest['condition']!=CONDITION or manifest['access']!=ACCESS:raise ValueError('Blueprint condition mismatch')
    verify({root/k:v for k,v in manifest['files'].items()})
    verify({SYSTEM/'prompts/blueprint.md':manifest['prompt_sha256']})
    run=root/'runs'/ident
    if not (run/'run.json').exists():
        single.prepare_work(run,item['domain'])
        for name in ('original_idea.json','research_record.json'):
            shutil.copy2(root/'inputs'/ident/name,run/'work'/name)
        (run/'work/evidence').mkdir()
        save(run/'work/debate/source_binding.json',dict(original_sha256=item['original_sha256'],manifest_sha256=sha(root/'manifest.json')))
        save(run/'run.json',dict(domain_id=item['domain'],access=ACCESS,condition=CONDITION,model='gpt-6-astra',effort='xhigh',created=now()))
    single.configure();original_bwrap=single.isolate.bwrap
    def bwrap(*args,**kwargs):
        command=original_bwrap(*args,**kwargs);i=command.index('--chdir')
        command[i:i]=['--ro-bind',str(root/'evidence'),'/work/evidence']
        return command
    single.isolate.bwrap=bwrap
    def resolve(path):
        path=Path(path)
        if path.is_absolute() or '..' in path.parts:raise ValueError('Use relative source paths within /work')
        if path.parts and path.parts[0]=='evidence':p=root/path
        elif str(path) in ('original_idea.json','research_record.json') or str(path).startswith('out/'):
            p=run/'work'/path
        else:raise ValueError('Unknown evidence source')
        if not p.is_file() or p.is_symlink():raise ValueError('Source file does not exist')
        return p
    def validate(value):
        if not isinstance(value.get('title'),str) or not value['title'].strip():raise ValueError('Missing title')
        sections=value.get('sections',[])
        if len(sections)!=9 or {s.get('number') for s in sections}!=set(range(1,10)):raise ValueError('Nine numbered sections required')
        if any(not isinstance(s.get('content'),str) or len(s['content'].strip())<80 for s in sections):raise ValueError('Incomplete section')
        if value.get('core_mechanism_status') not in ('preserved','uncertain','needs_revision'):raise ValueError('Missing mechanism check')
        for key in ('writer_additions','unresolved'):
            if not isinstance(value.get(key),list) or any(not isinstance(x,str) for x in value[key]):raise ValueError('Invalid '+key)
        if not isinstance(value.get('sources'),list) or not value['sources']:raise ValueError('Missing sources')
        for src in value['sources']:
            resolve(src['path'])
            if not all(isinstance(src.get(k),str) and src[k].strip() for k in ('reading_depth','used_for')):raise ValueError('Source reading depth and use required')
        if SECRET.search(json.dumps(value,ensure_ascii=False)):raise ValueError('Credential-like content rejected')
    prompt=(SYSTEM/'prompts/blueprint.md').read_text().replace('{api_base}',os.environ['LITGRAPH_API_BASE_URL'])+'''

本轮具体输入：/work/original_idea.json 是不可修改的入选原卡，/work/research_record.json 是从真实前序产物提取的显式证据索引。完整来源目录在 /work/evidence/index.json，检索日志在 /work/evidence/SEARCH_LOG.md；可按需读这些只读文件，不必全量重读。
这里没有原作者未保存的思考过程；历史未记录的论证桥梁必须标为写作阶段补充。
不能调用子代理，不能换卡。只在 /work/out 写交付和必要的新检索材料。
必须写 /work/out/RESEARCH_BLUEPRINT.json，JSON 对象字段：title；sections（九个对象，每项 number 为 1..9、content 为中文连贯正文，每节至少 80 字符）；sources（实际使用的来源，每项 path 为 /work 下相对路径、reading_depth、used_for）；writer_additions（字符串数组）；unresolved（字符串数组）；core_mechanism_status（preserved / uncertain / needs_revision）。
来源可以是 original_idea.json、research_record.json、evidence/ 中的真实文件或 out/ 中新增的检索证据；不要把尚未读取的文献写成全文已读。还须遵守此前的九节科学内容要求。系统将保留原卡并渲染中文研究方案，不需要自行重写原卡。
'''
    output=run/'work/out/RESEARCH_BLUEPRINT.json'
    receipt=invoke(run,'blueprint',prompt,output,validate)
    verify({root/k:v for k,v in manifest['files'].items()})
    value=read(output);dest=root/'deliveries'/f'idea-{item["rank"]:02}';dest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/'inputs'/ident/'original_idea.json',dest/'IDEA_CARD.json')
    shutil.copy2(output,dest/'RESEARCH_BLUEPRINT.json')
    record=read(root/'inputs'/ident/'research_record.json')
    record['writing_stage']={k:value[k] for k in ('writer_additions','unresolved','core_mechanism_status','sources')}
    save(dest/'research_record.json',record)
    md='# '+value['title']+'\n\n'
    for s in sorted(value['sections'],key=lambda x:x['number']):md+='## '+str(s['number'])+'. '+SECTIONS[s['number']-1]+'\n\n'+s['content']+'\n\n'
    md+='## 来源与阅读深度\n\n'+'\n'.join('- '+s['path']+'：'+s['reading_depth']+'；'+s['used_for'] for s in value['sources'])+'\n'
    (dest/'RESEARCH_BLUEPRINT.md').write_text(md)
    files={str(p):sha(p) for p in dest.iterdir() if p.is_file()}
    save(run/'completion.json',dict(at=now(),original_sha256=item['original_sha256'],files=files,output_dir=str(dest),
        native_session=receipt['session'],model='gpt-6-astra',effort='xhigh',provider=PROVIDER,access=ACCESS,
        selector_top1=item['selector_top1'],validation='Binding and structural checks; mechanism status is writer self-assessment'))
