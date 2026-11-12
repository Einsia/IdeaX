"""Parallelize only a contiguous independent block of native read_paper calls."""
from concurrent.futures import ThreadPoolExecutor

def candidates(tool_calls,start,remaining,parse_args,coerce_id):
    block=[];seen=set()
    for index in range(start,len(tool_calls)):
        if remaining is not None and len(block)>=remaining:break
        tc=tool_calls[index]
        if tc.get('function',{}).get('name')!='read_paper':break
        args,error=parse_args(tc)
        if error:break
        pid=coerce_id(args)
        # Unknown IDs and repeats stay sequential, preserving digest dependence.
        if pid is None or pid in seen:break
        seen.add(pid);block.append((index,tc,args,pid))
    return block

def execute(block,goal_union,run_tool,ctx,log):
    def one(item):
        index,tc,args,pid=item
        if pid in goal_union:args={**args,'goals':goal_union[pid]}
        try:return index,run_tool('read_paper',args,ctx,tool_call_id=tc['id'])
        except Exception as exc:
            log.event('tool_error',tool='read_paper',error=str(exc),tool_call_id=tc['id'])
            return index,f'ERROR in read_paper: {exc}'
    # Existing run-scoped per-paper locks serialize overlapping reader calls
    # across roles. Each thread owns one separate native model client.
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='native-reader') as pool:
        return dict(pool.map(one,block))
