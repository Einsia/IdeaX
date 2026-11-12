"""Continue a completed 48-turn native loop from its exact last tool boundary.

No candidate reroll, model-response synthesis, replayed file edits, or changed
scientific prompts. A single extension restores the native 100-turn default.
"""
import copy
import json
import shutil
from pathlib import Path
from common import read, save, sha, now, alive, process_handle
from replay_recovery import array

CHECKPOINT = 'continuation-v6.json'
ARCHIVE = 'before-continuation-v6'

def eligible(native):
    if (native/CHECKPOINT).exists() or (native/'idea_card.json').exists() or (native/'outputs/report.json').exists():return False
    if alive(read(native/'status.json').get('handle')):return False
    config=read(native/'run_config.json')
    if config.get('max_turns')!=48:return False
    events=array(native/'logs/harness_log.json')
    ends=[e for e in events if e.get('kind')=='loop_end']
    return bool(ends and ends[-1].get('reason')=='max_turns')

def build_checkpoint(native):
    events=array(native/'logs/harness_log.json')
    rows=array(native/'logs/llm_calls.json')
    last=rows[-1];summary=read(native/'logs/summary.json')
    ends=[e for e in events if e.get('kind')=='loop_end']
    if ends[-1].get('reason')!='max_turns':raise ValueError('Not a completed turn-budget boundary')
    next_turn=int(last['step'].split(':')[1])+1
    if ends[-1]['turn']!=next_turn:raise ValueError('Last model turn and loop boundary disagree')
    ids=[tc['id'] for tc in last.get('tool_calls',[]) or []]
    if not ids:raise ValueError('No completed tool boundary; manual checkpoint review required')
    matches=[]
    for path in (native/'request_cache').glob('*.json'):
        value=read(path);message=(value.get('choices') or [{}])[0].get('message',{})
        if [tc['id'] for tc in message.get('tool_calls',[]) or []]==ids:matches.append((path,message))
    if len(matches)!=1:raise ValueError('Need exactly one original cached assistant response')
    cache,assistant=matches[0]
    for old,new in zip(last['tool_calls'],assistant['tool_calls']):
        if old['name']!=new['function']['name'] or json.loads(old['args'])!=json.loads(new['function']['arguments']):
            raise ValueError('Cached assistant tool call differs from native log')
    results={e['tool_call_id']:e['result'] for e in events if e.get('kind')=='tool_result' and e.get('tool_call_id') and 'result' in e}
    spawns=[tc for tc in assistant['tool_calls'] if tc['function']['name']=='spawn_subagent']
    spawn_index=summary['subagents_spawned']-len(spawns)
    result_sources={}
    for tc in assistant['tool_calls']:
        tid=tc['id'];fn=tc['function']['name']
        if fn=='spawn_subagent':
            spawn_index+=1;role=json.loads(tc['function']['arguments'])['role']
            conversation=f'{role}#{spawn_index}'
            subpath=native/'logs/_sublogs'/f'{role}.json'
            subrows=[row for row in array(subpath) if row.get('conversation_id')==conversation]
            if not subrows or subrows[-1].get('tool_calls'):raise ValueError('Subagent did not leave an unambiguous final response')
            if not any(e.get('kind')=='subagent_done' and e.get('role')==role for e in events[-5:]):
                raise ValueError('Final subagent completion event missing')
            results[tid]=subrows[-1].get('response_content') or '(done)'
            result_sources[tid]=dict(path=str(subpath),conversation_id=conversation,step=subrows[-1]['step'])
        elif tid not in results:raise ValueError('Missing exact tool result: '+tid)
        else:result_sources[tid]=dict(path=str(native/'logs/harness_log.json'),tool_call_id=tid)
    messages=copy.deepcopy(last['input_messages'])+[copy.deepcopy(assistant)]
    for tc in assistant['tool_calls']:
        messages.append(dict(role='tool',tool_call_id=tc['id'],name=tc['function']['name'],content=results[tc['id']]))
    return dict(version=6,created_at=now(),policy='one same-history extension from 48 to native 100 orchestrator turns',
        next_turn=next_turn,old_max_turns=48,max_turns=100,max_sub_turns=40,
        restored_turns=read(native/'restored_turns.json',{}),messages=messages,summary=summary,
        orchestrator_nudges=sum(e.get('kind')=='orch_nudge' for e in events),
        assistant_cache=str(cache),assistant_cache_sha256=sha(cache),tool_result_sources=result_sources,
        output_hashes={str(p.relative_to(native)):sha(p) for p in (native/'outputs').rglob('*') if p.is_file()},
        log_hashes={str(p.relative_to(native)):sha(p) for p in (native/'logs').rglob('*') if p.is_file()},
        prompt_sha256=sha(native/'prompt_effective.md'))

def prepare(native):
    if (native/CHECKPOINT).exists():return read(native/CHECKPOINT)
    checkpoint=build_checkpoint(native)
    archive=native/ARCHIVE
    archive.mkdir(exist_ok=False)
    shutil.copytree(native/'outputs',archive/'outputs')
    for name in ('run_config.json','prompt_effective.md','status.json','delivery.json','restored_turns.json'):
        if (native/name).exists():shutil.copy2(native/name,archive/name)
    save(archive/'manifest.json',dict(at=now(),files={str(p.relative_to(archive)):sha(p) for p in archive.rglob('*') if p.is_file()},log_hashes=checkpoint['log_hashes']))
    save(native/CHECKPOINT,checkpoint)
    save(native/'recovery-ready-v2.json',dict(at=now(),recovery='continuation-v6',checkpoint=str(native/CHECKPOINT)))
    return checkpoint

def activate(native,problem):
    checkpoint=read(native/CHECKPOINT)
    if not checkpoint:return None
    if (native/'continuation-v6-started.json').exists():raise ValueError('Checkpoint already consumed; inspect new history before any retry')
    import hashlib
    if hashlib.sha256(problem.encode()).hexdigest()!=checkpoint['prompt_sha256']:raise ValueError('Continuation prompt changed')
    for relative,expected in {**checkpoint['output_hashes'],**checkpoint['log_hashes']}.items():
        if sha(native/relative)!=expected:raise ValueError('Checkpoint artifact changed: '+relative)
    if sha(Path(checkpoint['assistant_cache']))!=checkpoint['assistant_cache_sha256']:raise ValueError('Cached assistant response changed')
    (native/'logs').rename(native/ARCHIVE/'logs')
    save(native/'continuation-v6-started.json',dict(at=now(),next_turn=checkpoint['next_turn'],handle=process_handle(__import__('os').getpid()),checkpoint_sha256=sha(native/CHECKPOINT)))
    return checkpoint
