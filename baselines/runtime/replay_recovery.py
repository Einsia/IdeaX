"""Replay only previously completed model/tool calls within the SAME native run.

Model outputs come from the existing per-run request cache. Tool results are
keyed by their original call IDs, so replay cannot repeat file edits or spend
requests on completed readers. The first uncached call continues the original
history and artifacts. Nothing is borrowed from another proposal.
"""
import json
from pathlib import Path
from common import read, save, event

def array(path):
    if not path.exists():return []
    text=path.read_text().rstrip().rstrip(',')
    if not text.strip():return []
    for candidate in (text,text+'\n]'):
        try:return json.loads(candidate)
        except ValueError:pass
    raise ValueError('Cannot read durable native log records: '+str(path))

def prepare(native,archive):
    records=array(archive/'logs/harness_log.json');results={}
    for row in records:
        if row.get('kind')=='tool_result' and row.get('tool_call_id') and 'result' in row:
            results[row['tool_call_id']]=row['result']
        elif row.get('kind')=='tool_error' and row.get('tool_call_id'):
            results.setdefault(row['tool_call_id'],'ERROR in '+row.get('tool','')+': '+str(row.get('error','')))
    # Include earlier replay maps if a second transport repair is necessary.
    previous=read(native/'tool_replay.json',{})
    for key,value in previous.items():results.setdefault(key,value)
    save(native/'tool_replay.json',results)
    failed_ids={key for key,value in results.items() if any(word in str(value) for word in
                ('HTTP Error 503','HTTP Error 429','Service Unavailable','busy; retry later'))}
    restored={}
    paths=[archive/'logs/llm_calls.json',*sorted((archive/'logs/_sublogs').glob('*.json'))]
    seen=set()
    for path in paths:
        for row in array(path):
            step=row.get('step','')
            if not step or step in seen:continue
            outage=any(tc.get('id') in failed_ids for tc in row.get('tool_calls',[]) or [])
            if step.startswith('orch:'):
                recent=(row.get('input_messages') or [])[-1:]
                outage=outage or any(m.get('role')=='tool' and any(w in str(m.get('content','')) for w in
                    ('503','Service Unavailable','检索服务不可用','检索服务故障')) for m in recent)
            if outage:
                prefix=step.rsplit(':',1)[0];restored[prefix]=restored.get(prefix,0)+1;seen.add(step)
    save(native/'restored_turns.json',restored)
    return {'recorded_tool_results':len(results),'restored_infrastructure_turns':restored,
            'source':str(archive/'logs/harness_log.json')}

def restored_turns(native,prefix,cap):
    return min(cap,int(read(Path(native)/'restored_turns.json',{}).get(prefix,0)))

def install(native):
    from ideascientist.harness import tools
    results=read(native/'tool_replay.json',{})
    original=tools.run_tool
    def run_tool(name,args,ctx,tool_call_id=None):
        if tool_call_id and tool_call_id in results:
            value=results[tool_call_id]
            ctx.log.event('tool_result',tool=name,tool_call_id=tool_call_id,result=value,replayed=True)
            event(native/'replay_events.jsonl','completed_tool_result_replayed',tool=name,tool_call_id=tool_call_id)
            return value
        return original(name,args,ctx,tool_call_id=tool_call_id)
    tools.run_tool=run_tool
