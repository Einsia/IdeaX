"""Explicit user policy: terminal novelty rejection consumes one slot at score zero."""
from common import read,save,sha,now

REJECTION='RuntimeError: Novelty screening rejected all candidates within the configured retry budget'


def record_rejection(native,domain,index,log):
    lines=log.read_text(errors='replace').strip().splitlines()
    if not lines or lines[-1]!=REJECTION:raise ValueError('Not a terminal native novelty rejection')
    result=dict(id=f'coi-{domain}-{index:02}',method='coi',domain=domain,index=index,
        status='rejected_novelty',score=0,include_in_denominator=True,at=now(),
        reason='Native novelty screening rejected all candidates within the original retry budget',
        evidence=str(log),evidence_sha256=sha(log),policy='user-novelty-rejection-zero-20261107',
        generated_card=False,external_judge_called=False)
    path=native/'novelty_rejection.json'
    if path.exists():return read(path)
    save(path,result);return result


def aggregate(run):
    rows=[]
    for index in range(1,6):
        native=run/'native'/f'run-{index:02}';card=native/'idea_card.json';rejection=native/'novelty_rejection.json'
        if card.exists() and rejection.exists():raise ValueError('A slot cannot be both accepted and rejected')
        if card.exists():
            value=read(card);rows.append(dict(id=value['card_id'],index=index,status='generated',card=str(card),score=None,include_in_denominator=True))
        elif rejection.exists():
            value=read(rejection)
            if value.get('status')!='rejected_novelty' or value.get('score')!=0:raise ValueError('Invalid rejection outcome')
            if sha(value['evidence'])!=value['evidence_sha256']:raise ValueError('Native rejection evidence changed')
            rows.append(value)
    save(run/'idea_outcomes.json',rows);return rows
