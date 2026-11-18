"""Frozen Dr. Claw OpenRouter agent loop with Astra transport and local session I/O.

Native tool schemas, skill instructions, and selection rules are retained.
The authorized offline phase removes the backend turn cap and maps literature
tools to the shared frozen corpus. Desktop database/UI initialization is omitted.
"""
from __future__ import annotations
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
from common import AstraClient, save, read, single_prompt, NativeFailure, InfrastructureFailure, safe, event

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'sources/dr_claw'
COMMIT='37493cd93b12fbf34bed68c6c6402b6e19aaf6d2'
NODE=ROOT/'state/node-v22.16.0-linux-x64/bin/node'
RUNTIME=ROOT/'state/dr_claw_runtime'

def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def domain_sha(domain):
    return hashlib.sha256(json.dumps(domain,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def prepare_offline_recovery(domain,out,offline_corpus,offline_cli,allow_interrupted_request=False,*,_snapshot_only=False):
    """Bind an existing offline session; never accepts online history or a new sample."""
    out=Path(out).resolve()
    if not out.is_relative_to(ROOT):raise InfrastructureFailure('Recovery output must stay in this offline phase')
    protocol=read(out/'offline_protocol.json',{})
    policy=ROOT/'protocol/offline_environment.txt'
    if protocol.get('public_network') is not False or protocol.get('old_online_history_imported') is not False:
        raise InfrastructureFailure('Recovery requires an original offline session')
    if protocol.get('native_turn_limit',30) is not None or protocol.get('corpus')!=str(Path(offline_corpus).resolve()) or protocol.get('shared_literature_cli')!=str(Path(offline_cli).resolve()):
        raise InfrastructureFailure('Recovery corpus, tool service, or turn semantics changed')
    if protocol.get('environment_policy_sha256')!=file_sha(policy):
        raise InfrastructureFailure('Recovery cannot change the original environment policy')
    if read(out/'project/instance.json',{}).get('research_topic')!=single_prompt(domain):
        raise InfrastructureFailure('Recovery domain differs from the original offline task')
    native=read(out/'integration_manifest.json',{})
    if native.get('source_commit')!=COMMIT or native.get('native_max_turns',30) is not None:
        raise InfrastructureFailure('Recovery native source or turn limit mismatch')
    if read(out/'result.json',{}).get('status') in ('success','native_failure'):
        raise InfrastructureFailure('A terminal method result cannot be regenerated')
    sessions=list((out/'openrouter-sessions').glob('*.jsonl'))
    if len(sessions)!=1:raise InfrastructureFailure('Recovery requires one unambiguous original offline session')
    history=[json.loads(line) for line in sessions[0].read_text().splitlines() if line.strip()]
    if sum(message.get('role')=='user' for message in history)!=1:
        raise InfrastructureFailure('Recovery requires one original user instruction')
    pending_tools={};replay_tools=[]
    for message in history:
        if message.get('role')=='assistant':
            for call in message.get('tool_calls',[]):pending_tools[call['id']]=call
        elif message.get('role')=='tool':
            call=pending_tools.pop(message['tool_call_id'],None)
            if call is None:raise InfrastructureFailure('Recovery session has unmatched tool output')
            replay_tools.append({'name':call['function']['name'],'args':json.loads(call['function']['arguments']),'output':message['content']})
    if pending_tools:raise InfrastructureFailure('Recovery cannot repeat a tool whose execution result is unknown')
    request_paths=sorted((out/'api_requests').glob('*/request.json'))
    if not request_paths:raise InfrastructureFailure('Recovery has no original model requests')
    interrupted=[];bound=[out/'offline_protocol.json',out/'integration_manifest.json',out/'command.txt',sessions[0],policy,Path(offline_cli),Path(offline_corpus).parent/'manifest.json']
    for index,path in enumerate(request_paths):
        payload=read(path,{})
        digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if payload.get('model')!='gpt-6-astra' or payload.get('reasoning_effort')!='xhigh':
            raise InfrastructureFailure('Recovery model or reasoning effort changed')
        receipt=read(path.parent/'receipt.json',{})
        response=read(path.parent/'response.json')
        if receipt.get('status')=='completed' and response is not None:
            response_digest=hashlib.sha256(json.dumps(response,ensure_ascii=False).encode()).hexdigest()
            if receipt.get('request_sha256')!=digest or receipt.get('response_sha256')!=response_digest:
                raise InfrastructureFailure('Recovery completed request or response hash mismatch')
        else:
            if receipt.get('status')=='native_failure' or response is not None or index!=len(request_paths)-1 or not allow_interrupted_request:
                raise InfrastructureFailure('Only the final explicitly authorized interrupted request may be retried')
            attempts=list((path.parent/'attempts').glob('*'))
            if not attempts or len(attempts)>=5:raise InfrastructureFailure('Interrupted request has no remaining original retry budget')
            for stream in (path.parent/'attempts').glob('*/stream.jsonl'):
                for line in stream.read_text().splitlines():
                    chunk=json.loads(line)
                    if any(choice.get('finish_reason') is not None for choice in chunk.get('choices',[])):
                        raise InfrastructureFailure('Terminal stream exists; reconstruct it before considering a retry')
            interrupted.append({'request_id':path.parent.name,'request_sha256':digest,'prior_attempts':len(attempts),
                'retry_physical_requests_allowed':1,'reason':'Mount isolation patch interrupted response before terminal receipt',
                'original_response_preserved':False,'usage':None,'usage_known':False})
        bound.extend(path.parent.rglob('*'))
    bound.extend((out/'project').rglob('*'))
    bindings={str(path.resolve()):file_sha(path) for path in bound if path.is_file() and not path.is_symlink()}
    manifest={'protocol_id':'offline-common-corpus-20261117','output_dir':str(out),'domain_sha256':domain_sha(domain),
        'source_session':str(sessions[0]),'request_ids':[path.parent.name for path in request_paths],
        'replay_tools':replay_tools,'bindings':bindings,'interrupted_requests':interrupted,
        'completed_responses_reused':len(request_paths)-len(interrupted),'old_online_history_imported':False,
        'same_slot':True,'fresh_sampling':False,'completed_tools_reexecuted':False}
    if _snapshot_only:return manifest
    target=out/'offline_recovery_manifest.json'
    if target.exists():raise InfrastructureFailure('Recovery manifest already exists; preserve the original recovery attempt')
    save(target,manifest)
    return target

def validate_offline_recovery(path,domain,out,offline_corpus=None,offline_cli=None):
    path=Path(path).resolve();out=Path(out).resolve()
    if not path.is_relative_to(out):raise InfrastructureFailure('Offline recovery manifest must be inside the same slot')
    value=read(path,{})
    if value.get('protocol_id')!='offline-common-corpus-20261117' or value.get('output_dir')!=str(out) or value.get('domain_sha256')!=domain_sha(domain) or value.get('old_online_history_imported') is not False:
        raise InfrastructureFailure('Offline recovery identity mismatch')
    if (out/'offline_recovery_started.json').exists():raise InfrastructureFailure('This offline recovery was already attempted; automatic repeat is forbidden')
    if not value.get('bindings'):raise InfrastructureFailure('Offline recovery lacks frozen evidence')
    for name,digest in value['bindings'].items():
        bound=Path(name)
        if not bound.is_file() or file_sha(bound)!=digest:raise InfrastructureFailure('Offline recovery bound file changed: '+name)
    actual=[item.parent.name for item in sorted((out/'api_requests').glob('*/request.json'))]
    if actual!=value.get('request_ids'):raise InfrastructureFailure('Offline recovery request sequence changed')
    protocol=read(out/'offline_protocol.json',{})
    expected=prepare_offline_recovery(domain,out,offline_corpus or protocol.get('corpus',''),offline_cli or protocol.get('shared_literature_cli',''),
        bool(value.get('interrupted_requests')),_snapshot_only=True)
    if expected!=value:raise InfrastructureFailure('Offline recovery manifest does not match the original native session')
    return value

def validate_native_artifacts(idea_dir):
    """Check the artifact and promotion contract in the frozen native skill."""
    required=['idea_context.md','idea_slate.md','idea_query_round_1.txt',
              'raw_idea_1.txt','raw_idea_2.txt','raw_idea_3.txt',
              'selected_idea.txt','idea_ledger.md',
              'logs/idea_generation_agent.json','logs/idea_generation_agent_iter_1.json',
              'logs/idea_generation_agent_iter_2.json','logs/idea_generation_agent_iter_select.json']
    errors=[]
    missing=[name for name in required if not (idea_dir/name).is_file() or not (idea_dir/name).stat().st_size]
    if missing:return {'passed':False,'errors':['Missing native artifacts: '+', '.join(missing)],'required_artifacts':required}
    try:
        for index,name in enumerate(required[8:11],1):
            ctx=json.loads((idea_dir/name).read_text())['context_variables']
            history=ctx['idea_generation_history']
            entry=next(x for x in history if x.get('round')==index)
            if entry['content'].strip()!=(idea_dir/f'raw_idea_{index}.txt').read_text().strip():
                errors.append(f'Candidate {index} native log does not preserve its full proposal')
            if not entry.get('family'):errors.append(f'Candidate {index} lacks native direction-family record')
        ctx=json.loads((idea_dir/required[-1]).read_text())['context_variables']
        selected=ctx['final_selected_idea_data']
        if selected['selected_idea_text'].strip()!=(idea_dir/'selected_idea.txt').read_text().strip():
            errors.append('Native selection log does not preserve the full selected proposal')
        scores=selected['gate_scores'];keys=['novelty','falsifiability','feasibility','evidence','constraint_fit']
        values=[scores[k] for k in keys]
        if any(type(v) is not int or v not in (1,2) for v in values):errors.append('Native gate has a zero or invalid criterion score')
        if scores['total']!=sum(values) or scores['total']<7:errors.append('Native gate total is inconsistent or below 7/10')
        label=selected['novelty_label'].lower().strip().replace('(unverified)','').strip()
        if label not in ('novel','incremental but valuable'):errors.append('Native novelty label is not eligible for selection')
        details={'gate_scores':scores,'novelty_label':selected['novelty_label']}
    except (KeyError,TypeError,ValueError,StopIteration) as exc:
        errors.append('Malformed native artifact log: '+str(exc));details={}
    return {'passed':not errors,'errors':errors,'required_artifacts':required,**details}

def runtime(out, replay=False, unbounded=False, offline=False):
    """Extract native module with only app integration imports replaced."""
    s=(SOURCE/'server/openrouter.js').read_text()
    replaced=[]
    kept=[]
    for line in s.splitlines():
        if line.startswith('import ') and ('from \'./' in line or 'from \'../' in line):
            replaced.append(line)
        else:kept.append(line)
    s='\n'.join(kept)+'\n'
    if unbounded:
        replacements = {
            'const MAX_AGENT_TURNS = 30;\n': '',
            'while (turn < MAX_AGENT_TURNS) {': 'while (true) {',
            'console.log(`[OpenRouter] Turn ${turn}/${MAX_AGENT_TURNS} · model=${model} · msgs=${messages.length}`);':
                'console.log(`[OpenRouter] Turn ${turn} · model=${model} · msgs=${messages.length}`);',
            '    if (turn >= MAX_AGENT_TURNS) {\n      console.warn(`[OpenRouter] Reached max agent turns (${MAX_AGENT_TURNS})`);\n    }\n': '',
        }
        for before, after in replacements.items():
            if s.count(before) != 1:
                raise InfrastructureFailure('Frozen native turn-cap patch no longer matches source')
            s = s.replace(before, after, 1)
        if 'MAX_AGENT_TURNS' in s:
            raise InfrastructureFailure('A native turn-limit reference remains')
    if offline:
        if not unbounded:
            raise InfrastructureFailure('The new offline phase must use the authorized uncapped loop')
        start=s.index("      case 'WebFetch': {")
        end=s.index("      case 'TodoWrite': {",start)
        s=s[:start]+'''      case 'WebFetch': {
        return trunc(await offlineLiteratureTool('read', {url: args.url}));
      }

      case 'WebSearch': {
        return trunc(await offlineLiteratureTool('search', {query: args.query}));
      }

'''+s[end:]
        s=s.replace("description: 'Fetch the text content of a URL.'", "description: 'Read matching original text from the frozen local literature corpus. Public network access is disabled.'")
        s=s.replace("description: 'Search the web using a query. Returns summarized results.'", "description: 'Search the frozen local literature corpus using a query. Returns local source records; public network access is disabled.'")
    prelude=f'''import spawnAsync from {json.dumps(str(RUNTIME/'server/utils/spawnAsync.js'))};
import {{ safePath }} from {json.dumps(str(RUNTIME/'server/utils/safePath.js'))};
import {{ COMPUTE_GUARD_BLOCK }} from {json.dumps(str(RUNTIME/'server/utils/computeGuardPrompt.js'))};
import {{ writeProjectTemplates }} from {json.dumps(str(RUNTIME/'server/templates/index.js'))};
import {{ expandSkillCommand }} from {json.dumps(str(RUNTIME/'server/utils/skillExpander.js'))};
import {{ collectSkillDirs, syncProjectSkillLinks }} from {json.dumps(str(RUNTIME/'server/utils/skillLinks.js'))};
import {{ readSkillManifest, resolveSkillStates }} from {json.dumps(str(RUNTIME/'server/utils/skillDefaults.js'))};
import {{ classifyError }} from {json.dumps(str(RUNTIME/'shared/errorClassifier.js'))};
import {{ createRequestId, waitForToolApproval, matchesToolPermission }} from {json.dumps(str(RUNTIME/'server/utils/permissions.js'))};
const encodeProjectPath = p => p;
const ensureProjectSkillLinks = async projectPath => {{
  const skillsRoot = path.join(projectPath,'skill_library');
  const skillDirs = await collectSkillDirs(skillsRoot);
  const manifest = readSkillManifest(skillsRoot);
  const states = resolveSkillStates({{skillNames:skillDirs.map(s=>s.name),manifest,globalPrefs:{{baseline:'recommended',overrides:{{}},knownSkills:[]}}}});
  await syncProjectSkillLinks({{projectPath,skillsRoot,skillDirs,enabledNames:new Set(states.filter(s=>s.enabled).map(s=>s.name)),coreNames:manifest.coreNames,folders:['.claude','.agents','.cursor','.gemini']}});
}};
const reconcileOpenRouterSessionIndex = async () => {{}};
const applyStageTagsToSession = () => {{}};
const recordIndexedSession = () => {{}};
const buildMemoryBlock = () => '';
'''
    if offline:
        prelude+='''
async function offlineLiteratureTool(action, args) {
  const response = await fetch(process.env.DRCLAW_TRANSPORT_URL + '/offline/' + action, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(args)
  });
  const result = await response.text();
  if (!response.ok) return 'Local corpus error: ' + result;
  return result;
}
'''
    # Redirect only service route and session persistence; no changes to agent control flow.
    s=s.replace("const OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1';", "const OPENROUTER_BASE_URL = process.env.DRCLAW_TRANSPORT_URL;")
    s=s.replace("path.join(os.homedir(), '.dr-claw', SESSIONS_DIR_NAME)", "path.join(process.env.DRCLAW_OUTPUT_DIR, SESSIONS_DIR_NAME)")
    if replay:
        s=s.replace('async function executeTool(name, args, workingDir) {','async function executeToolNative(name, args, workingDir) {',1)
        prelude+='''
const replayTools = JSON.parse(await fs.readFile(process.env.DRCLAW_OUTPUT_DIR+'/infrastructure_replay_tools.json','utf8'));
let replayToolIndex = 0;
function stableJson(v) {
  if (Array.isArray(v)) return '['+v.map(stableJson).join(',')+']';
  if (v && typeof v === 'object') return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stableJson(v[k])).join(',')+'}';
  return JSON.stringify(v);
}
async function executeTool(name,args,workingDir) {
  if (replayToolIndex < replayTools.length) {
    const expected=replayTools[replayToolIndex++];
    if (name !== expected.name || stableJson(args) !== stableJson(expected.args)) throw new Error('Infrastructure replay tool mismatch at '+replayToolIndex);
    await fs.appendFile(process.env.DRCLAW_OUTPUT_DIR+'/infrastructure_replay_events.jsonl',JSON.stringify({event:'cached_tool_output',index:replayToolIndex,name})+'\\n');
    return expected.output;
  }
  return executeToolNative(name,args,workingDir);
}
'''
    s=prelude+s+'''\nexport async function preflightProject(project,command) {
  await ensureProjectSkillLinks(project);
  await writeProjectTemplates(project);
  await fs.writeFile(process.env.DRCLAW_OUTPUT_DIR+'/preflight_system_prompt.txt',await buildSystemPrompt(project));
  await fs.writeFile(process.env.DRCLAW_OUTPUT_DIR+'/preflight_expanded_command.txt',await expandSkillCommand(command,project));
}\n''' 
    module=out/'native_openrouter.mjs';module.write_text(s)
    save(out/'integration_manifest.json',{'source_commit':COMMIT,'source_file':'server/openrouter.js',
        'source_sha256':hashlib.sha256((SOURCE/'server/openrouter.js').read_bytes()).hexdigest(),
        'runtime_sha256':hashlib.sha256(s.encode()).hexdigest(),'replaced_app_imports':replaced,
        'transport':'common AstraClient streaming completion -> native stream parser',
        'native_max_turns':None if unbounded else 30,'turn_limit_removed':unbounded,
        'termination':'Native no-tool final answer, explicit cancellation, transport or process failure; no replacement fixed turn cap' if unbounded else 'Original frozen 30-turn cap',
        'offline_literature_tools':offline,'app_changes':['desktop session index hooks no-op','isolated session directory','native templates, skill expansion and recommended skill defaults retained'],
        'selection':'official inno-idea-generation; 3 candidates, fresh-context reread, 7/10 no-zero gate'})
    return module

def run(domain,out,dry=False,resume_infrastructure=False,unbounded=False,offline_corpus=None,offline_cli=None,offline_recovery=None):
    out.mkdir(parents=True,exist_ok=True)
    offline=offline_corpus is not None
    recovery=None
    if offline_recovery and not offline:raise InfrastructureFailure('Offline recovery cannot be used outside the offline protocol')
    if offline:
        if os.environ.get('INSIGHTPRO_OFFLINE_ENFORCED') != '1' or not os.environ.get('INSIGHTPRO_OFFLINE_PHASE'):
            raise InfrastructureFailure('Offline execution requires the shared enforced network wrapper')
        offline_phase=Path(os.environ['INSIGHTPRO_OFFLINE_PHASE']).resolve()
        offline_policy=offline_phase/'protocol/offline_environment.txt'
        if not offline_policy.is_file() or not out.resolve().is_relative_to(offline_phase):
            raise InfrastructureFailure('Offline output and shared environment policy must belong to the isolated phase')
        if resume_infrastructure:
            raise InfrastructureFailure('Offline phase starts a fresh session; online histories cannot be resumed')
        if not offline_cli or not Path(offline_cli).is_file() or not Path(offline_corpus).is_file():
            raise InfrastructureFailure('Frozen local literature corpus and shared CLI are required')
        if offline_recovery:
            if dry:raise InfrastructureFailure('Recovery is an exact continuation, not a preflight run')
            recovery=validate_offline_recovery(offline_recovery,domain,out,offline_corpus,offline_cli)
        elif list((out/'api_requests').glob('*/request.json')) or list((out/'openrouter-sessions').glob('*.jsonl')):
            raise InfrastructureFailure('Offline run requires a fresh session and request directory')
        unbounded=True
    replay_requests=[]
    if recovery:
        replay_requests=[out/'api_requests'/ident/'request.json' for ident in recovery['request_ids']]
        archive=out/'infrastructure_recovery'/str(__import__('time').time_ns());archive.mkdir(parents=True)
        for name in ['result.json','events.json','integration_manifest.json','native_openrouter.mjs','entry.mjs','offline_protocol.json']:
            if (out/name).exists():shutil.copy2(out/name,archive/name)
        shutil.copy2(recovery['source_session'],archive/Path(recovery['source_session']).name)
        save(out/'infrastructure_replay_tools.json',recovery['replay_tools'])
        save(out/'offline_recovery_started.json',{'manifest':str(Path(offline_recovery).resolve()),'manifest_sha256':file_sha(offline_recovery),
            'source_session':recovery['source_session'],'archived_evidence':str(archive),'request_ids':recovery['request_ids'],
            'completed_responses_reused':recovery['completed_responses_reused'],'completed_tools_reexecuted':False,
            'interrupted_requests':recovery['interrupted_requests']})
    if resume_infrastructure:
        prior=read(out/'result.json',{})
        if prior.get('status')!='infrastructure_failure':raise InfrastructureFailure('Only infrastructure failures permit same-request replay')
        events=read(out/'events.json',[])
        failure=next((e for e in reversed(events) if e.get('type')=='openrouter-error'),None)
        if not failure:raise InfrastructureFailure('Missing native backend error event for replay')
        archive=out/'infrastructure_recovery'/str(__import__('time').time_ns());archive.mkdir(parents=True)
        for name in ['result.json','events.json','integration_manifest.json','native_openrouter.mjs','entry.mjs']:
            if (out/name).exists():shutil.copy2(out/name,archive/name)
        session=out/'openrouter-sessions'/(failure['sessionId']+'.jsonl')
        shutil.copy2(session,archive/session.name)
        history=[json.loads(line) for line in session.read_text().splitlines() if line.strip()]
        pending={};replay_tools=[]
        for message in history:
            if message.get('role')=='assistant':
                for call in message.get('tool_calls',[]):pending[call['id']]=call
            elif message.get('role')=='tool':
                call=pending.pop(message['tool_call_id'])
                replay_tools.append({'name':call['function']['name'],'args':json.loads(call['function']['arguments']),'output':message['content']})
        if pending:raise InfrastructureFailure('Cannot replay an incomplete tool execution')
        save(out/'infrastructure_replay_tools.json',replay_tools)
        replay_requests=sorted((out/'api_requests').glob('*/request.json'))
        save(out/'infrastructure_replay_manifest.json',{'original_session':str(session),'archived_evidence':str(archive),
             'request_ids':[p.parent.name for p in replay_requests],'cached_tool_outputs':len(replay_tools),
             'successful_responses_reused':sum((p.parent/'response.json').exists() for p in replay_requests),
             'native_turn_limit_unchanged':30,'reexecute_completed_tools':False})
    project=out/'project';project.mkdir(exist_ok=True)
    library=project/'skill_library'
    if not library.exists():shutil.copytree(SOURCE/'skills',library)
    idea_dir=project/'Ideation/ideas';idea_dir.mkdir(parents=True,exist_ok=True)
    refs=project/'Ideation/references';refs.mkdir(parents=True,exist_ok=True)
    instance={'research_topic':single_prompt(domain),'category':'machine learning','instance':str(project/'instance.json')}
    layout={'Survey':['references','reports'],'Ideation':['ideas','references'],'Experiment':['code_references','datasets','core_code','analysis'],'Publication':['paper'],'Promotion':['homepage','slides','audio','video']}
    for group,names in layout.items():
        instance[group]={name:str(project/group/name) for name in names}
        for name in names:(project/group/name).mkdir(parents=True,exist_ok=True)
    save(project/'instance.json',instance)
    save(project/'.pipeline/docs/research_brief.json',{'meta':{'target_venue':'unspecified','research_topic':single_prompt(domain)},'pipeline':{'startStage':'ideation'},'sections':{'ideation':{'research_goal':single_prompt(domain),'problem_framing':domain.get('scope_boundary',''),'success_criteria':'One selected, falsifiable proposal with original native selection gate.'}}})
    save(project/'.pipeline/tasks/tasks.json',{'tasks':[{'id':'native-ideation','title':'Generate and select one research proposal','status':'pending','stage':'ideation','dependencies':[],'suggestedSkills':['inno-idea-generation'],'nextActionPrompt':single_prompt(domain)}]})
    save(project/'.pipeline/config.json',{'intakeCompleted':True})
    command='/inno-idea-generation '+single_prompt(domain)
    command+='\n\nThe requested deliverable is the selected research proposal. Stop after inno-idea-generation Step 5; do not implement, train, or run experiments. The task permits choosing a concrete problem and setting within the stated domain. All skill files are in .agents/skills; use their full instructions and prompt templates.\n'
    if offline:
        command+='\n\n'+offline_policy.read_text(encoding='utf-8')
    if recovery and command!=(out/'command.txt').read_text():raise InfrastructureFailure('Offline recovery command changed')
    (out/'command.txt').write_text(command)
    module=runtime(out,replay=resume_infrastructure or bool(recovery),unbounded=unbounded,offline=offline)
    entry=out/'entry.mjs'
    entry.write_text(f'''import {{ queryOpenRouter }} from {json.dumps(str(module))};
import {{ promises as fs }} from 'fs';
const output = process.env.DRCLAW_OUTPUT_DIR;
const events = [];
const writer = {{isSSEStreamWriter:true,send(data){{events.push(data);}}}};
if (process.env.DRCLAW_PREFLIGHT === '1') {{
  const mod=await import({json.dumps(str(module))});
  await mod.preflightProject(output+'/project',await fs.readFile(output+'/command.txt','utf8'));
  process.exit(0);
}}
await queryOpenRouter(await fs.readFile(output+'/command.txt','utf8'), {{cwd:output+'/project',model:'gpt-6-astra',env:{{OPENROUTER_API_KEY:'LOCAL_TRANSPORT_NO_CREDENTIAL'}},permissionMode:'bypassPermissions',toolsSettings:{{skipPermissions:true}}}}, writer);
await fs.writeFile(output+'/events.json',JSON.stringify(events,null,2));
process.exit(0);
''')
    if offline and not recovery:
        save(out/'offline_protocol.json',{'public_network':False,'model_api_via_host_unix_bridge':True,
            'corpus':str(Path(offline_corpus).resolve()),'shared_literature_cli':str(Path(offline_cli).resolve()),
            'environment_policy':str(offline_policy),'environment_policy_sha256':hashlib.sha256(offline_policy.read_bytes()).hexdigest(),
            'search_read_semantics':'Shared frozen original-text search/read; no public fallback',
            'old_online_history_imported':False,'native_turn_limit':None,
            'network_isolation':'Required shared offline phase wrapper encloses the adapter and all native descendants; this adapter does not create a second namespace'})
    check=subprocess.run([str(NODE),'--check',str(module)],capture_output=True,text=True)
    if check.returncode:raise InfrastructureFailure(check.stderr)
    env=dict(os.environ);env.pop('OPENAI_API_KEY',None);env.pop('OPENROUTER_API_KEY',None)
    env.update(DRCLAW_OUTPUT_DIR=str(out),DR_CLAW_USER_SKILLS_DIR=str(library))
    if dry:
        env['DRCLAW_PREFLIGHT']='1'
        check=subprocess.run([str(NODE),str(entry)],cwd=project,env=env,text=True,capture_output=True)
        if check.returncode:raise InfrastructureFailure(check.stderr)
        return {'status':'preflight_ok','proposal_markdown':None,'native_output_paths':[str(out/'preflight_system_prompt.txt'),str(out/'preflight_expanded_command.txt')],'terminal_reason':None,'native_commit':COMMIT}
    client=AstraClient(out)
    transport_errors=[]
    replay_request_index=0
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            nonlocal replay_request_index
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path.startswith('/offline/'):
                if not offline or self.path not in ('/offline/search','/offline/read'):
                    self.send_error(404);return
                action=self.path.rsplit('/',1)[-1]
                args=['python3',str(offline_cli),'--corpus',str(offline_corpus),action]
                args += ['--query',str(payload.get('query','')),'--limit','8'] if action=='search' else ['--id',str(payload.get('url',''))]
                result=subprocess.run(args,capture_output=True,text=True,timeout=60)
                try:
                    json.loads(result.stdout)
                    body=result.stdout
                except ValueError:
                    body=json.dumps({'error':'Local corpus operation failed','detail':result.stderr[-2000:]})
                data=body.encode()
                self.send_response(200 if result.returncode==0 else 400);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data);return
            if self.path!='/chat/completions':
                self.send_error(404);return
            # The native fetch client has a finite headers/body idle timeout.
            # Deliver SSE headers and harmless comments immediately while the
            # shared transport collects the exact native completion.
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Connection','close')
            self.end_headers();self.wfile.flush()
            heartbeat_done=threading.Event();write_lock=threading.Lock()
            def heartbeat():
                while not heartbeat_done.wait(10):
                    try:
                        with write_lock:self.wfile.write(b': transport pending\n\n');self.wfile.flush()
                    except (BrokenPipeError,ConnectionResetError):break
            heartbeat_thread=threading.Thread(target=heartbeat,daemon=True);heartbeat_thread.start()
            try:
                request_id=None
                if replay_request_index<len(replay_requests):
                    old_path=replay_requests[replay_request_index];old=json.loads(old_path.read_text())
                    for key in ['messages','tools','tool_choice']:
                        if old.get(key)!=payload.get(key):raise InfrastructureFailure('Native replay request mismatch: '+key+' at '+old_path.parent.name)
                    request_id=old_path.parent.name;replay_request_index+=1
                interrupted=next((item for item in recovery['interrupted_requests'] if item['request_id']==request_id),None) if recovery else None
                previous_attempts=client.max_attempts if interrupted else None
                if interrupted:
                    # Root authorized exactly one retry of the interrupted identical input.
                    client.max_attempts=1
                    event(out/'offline_recovery_events.jsonl','interrupted_exact_request_retry',**interrupted)
                try:
                    data=client.completion(payload['messages'],tools=payload.get('tools'),tool_choice=payload.get('tool_choice'),request_id=request_id)
                finally:
                    if interrupted:client.max_attempts=previous_attempts
                choice=data['choices'][0]
                message=choice['message']
                delta={'role':'assistant','content':message.get('content') or ''}
                if message.get('tool_calls'):
                    delta['tool_calls']=[{'index':i,**tc} for i,tc in enumerate(message['tool_calls'])]
                chunks=[{'id':data.get('id'),'model':data.get('model'),'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                        {'id':data.get('id'),'model':data.get('model'),'choices':[{'index':0,'delta':{},'finish_reason':choice.get('finish_reason')}],'usage':data.get('usage',{})}]
                body=(''.join('data: '+json.dumps(x)+'\n\n' for x in chunks)+'data: [DONE]\n\n').encode()
                heartbeat_done.set()
                with write_lock:self.wfile.write(body);self.wfile.flush()
            except Exception as exc:
                transport_errors.append({'type':type(exc).__name__,'error':safe(exc)})
                save(out/'transport_errors.json',transport_errors)
                heartbeat_done.set()
                body=('data: '+json.dumps({'error':{'message':safe(exc)}})+'\n\ndata: [DONE]\n\n').encode()
                try:
                    with write_lock:self.wfile.write(body);self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):pass
            finally:
                heartbeat_done.set();self.close_connection=True
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    env.update(DRCLAW_OUTPUT_DIR=str(out),DRCLAW_TRANSPORT_URL=f'http://127.0.0.1:{server.server_address[1]}')
    # Native Bash receives no model credentials and uses only the proposal workspace.
    try:
        proc=subprocess.run([str(NODE),str(entry)],cwd=project,env=env)
    finally:
        server.shutdown();server.server_close()
    selected=idea_dir/'selected_idea.txt'
    candidates=[idea_dir/f'raw_idea_{i}.txt' for i in range(1,4)]
    events=json.loads((out/'events.json').read_text()) if (out/'events.json').exists() else []
    native_errors=[e for e in events if e.get('type')=='openrouter-error']
    if transport_errors:
        status='native_failure' if all(e['type']=='NativeFailure' for e in transport_errors) else 'infrastructure_failure'
        return {'status':status,'proposal_markdown':None,'native_output_paths':[str(project)],'terminal_reason':transport_errors[-1]['error'],'native_commit':COMMIT}
    if native_errors:
        return {'status':'infrastructure_failure','proposal_markdown':None,'native_output_paths':[str(project),str(out/'events.json')],
                'terminal_reason':'Native backend error: '+str(native_errors[-1].get('error')),'native_commit':COMMIT}
    if proc.returncode or not selected.exists() or not all(p.exists() for p in candidates) or not (idea_dir/'idea_ledger.md').exists():
        return {'status':'native_failure','proposal_markdown':None,'native_output_paths':[str(project)],'terminal_reason':('Native loop terminated without all 3 candidates, selection ledger, and selected proposal' if unbounded else 'Native 30-turn loop ended without all 3 candidates, selection ledger, and selected proposal'),'native_commit':COMMIT}
    artifact_check=validate_native_artifacts(idea_dir)
    save(out/'native_artifact_validation.json',artifact_check)
    if not artifact_check['passed']:
        return {'status':'native_failure','proposal_markdown':None,'native_output_paths':[str(project)],'terminal_reason':'; '.join(artifact_check['errors']),'native_commit':COMMIT}
    text=selected.read_text()
    gate=re.search(r'gate\s*(?:\*\*)?\s*(7|8|9|10)\s*/\s*10',text,re.I)
    selection=re.search(r'\*\*Selection:\*\*([\s\S]*?)(?=\n\s*##|\Z)',text,re.I)
    selection_text=selection.group(1) if selection else ''
    scores=[]
    for label in ['novelty','falsifiability','feasibility','evidence','constraint fit']:
        value=re.search(re.escape(label)+r'\s*[:=]?\s*([012])\b',selection_text,re.I)
        if value:scores.append(int(value.group(1)))
    invalid_scores=len(scores)==5 and (0 in scores or (gate and sum(scores)!=int(gate.group(1))))
    invalid_label='not sufficiently differentiated' in selection_text.lower()
    if not gate or invalid_scores or invalid_label:
        return {'status':'native_failure','proposal_markdown':None,'native_output_paths':[str(project)],'terminal_reason':'Native selected proposal lacks required passing selection gate line','native_commit':COMMIT}
    (out/'proposal.md').write_text(text)
    return {'status':'success','proposal_markdown':str(out/'proposal.md'),'native_output_paths':[str(selected),str(idea_dir/'idea_ledger.md')]+list(map(str,candidates)),'terminal_reason':None,'native_commit':COMMIT}

def main():
    p=argparse.ArgumentParser();p.add_argument('--domain-json',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--dry-run',action='store_true');p.add_argument('--resume-infrastructure',action='store_true');p.add_argument('--uncapped',action='store_true');p.add_argument('--offline-corpus',type=Path);p.add_argument('--offline-cli',type=Path);p.add_argument('--offline-recovery',type=Path);p.add_argument('--prepare-offline-recovery',action='store_true');p.add_argument('--allow-interrupted-request',action='store_true');a=p.parse_args()
    if a.prepare_offline_recovery:
        if not a.offline_corpus or not a.offline_cli:p.error('Offline recovery preparation requires the original corpus and CLI')
        print(prepare_offline_recovery(json.loads(a.domain_json.read_text()),a.output_dir,a.offline_corpus,a.offline_cli,a.allow_interrupted_request));return 0
    try:result=run(json.loads(a.domain_json.read_text()),a.output_dir.resolve(),a.dry_run,a.resume_infrastructure,a.uncapped,a.offline_corpus,a.offline_cli,a.offline_recovery)
    except Exception as exc:result={'status':'native_failure' if isinstance(exc,NativeFailure) else 'infrastructure_failure','proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(exc)}
    save(a.output_dir/'result.json',result);print(json.dumps(result))
    return 0 if result['status'] in ('success','preflight_ok') else 2
if __name__=='__main__':raise SystemExit(main())
