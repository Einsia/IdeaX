"""Persist completed native phases only, scoped to a single independent run."""
import asyncio
import json
from pathlib import Path

STATE = ('read_papers', 'paper_info_for_refine_experiment', 'search_qeuries',
         'deep_research_chains', 'deep_ideas', 'check_novel_results', 'score_results', 'topic')

def checkpoint(name, agent, call):
    folder = Path('.stage_cache')
    folder.mkdir(exist_ok=True)
    path = folder / (name + '.json')
    if path.exists():
        row = json.loads(path.read_text())
        for key, value in row['state'].items():
            setattr(agent, key, set(value) if key == 'read_papers' else value)
        print('completed_native_stage_restored:', name, flush=True)
        return row['result']
    result = asyncio.run(call())
    state = {key: sorted(getattr(agent, key)) if key == 'read_papers' else getattr(agent, key) for key in STATE}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'result': result, 'state': state}, ensure_ascii=False))
    temporary.replace(path)
    print('completed_native_stage_saved:', name, flush=True)
    return result
