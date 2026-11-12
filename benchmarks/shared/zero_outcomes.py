"""Keep verified generation rejections separate from judge assessments."""
from collections import Counter
import hashlib
import json
from pathlib import Path

def load(source):
    path=Path(source).parent/'zero_score_outcomes.json'
    if not path.exists():return []
    rows=json.loads(path.read_text());verify(rows);return rows

def verify(rows):
    seen=set()
    for row in rows:
        key=(row['system'],row['task_id'],row['id'])
        if key in seen:raise ValueError('Duplicate rejected slot')
        seen.add(key)
        if row.get('status')!='rejected_novelty' or row.get('score')!=0 or row.get('generated_card') is not False:
            raise ValueError('Only terminal native novelty rejection may contribute zero')
        path=Path(row['evidence'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['evidence_sha256']:
            raise ValueError('Rejection evidence changed')
        if path.read_text(errors='replace').strip().splitlines()[-1:]!=[
            'RuntimeError: Novelty screening rejected all candidates within the configured retry budget']:
            raise ValueError('Not a verified terminal native novelty rejection')

def adjusted(summary,zeros,complete):
    verify(zeros)
    counts=Counter(x['system'] for x in zeros)
    result=[]
    for group in summary:
        n=group['count'];z=counts[group['system']]
        result.append({'system':group['system'],'judge':group['judge'],'generated':n,'rejected_novelty':z,
            'denominator':n+z,'means':{k:v*n/(n+z) if complete and v is not None and n+z else None
                                     for k,v in group['means'].items()},
            'policy':'verified_native_novelty_rejections_zero; API failures and missing judgments remain incomplete'})
    return result
