"""Accept a lossless native report schema mapping; never invent missing content."""
from pathlib import Path
import os
from common import *
from citations import extract

REQUIRED=('title','one_sentence_thesis','core_problem','key_novelty','method',
          'proposed_evaluation','falsifiable_predictions','limitations')
ALIASES={
    'title':('proposal.title',),
    'one_sentence_thesis':('proposal.one_sentence_thesis','proposal.core_hypothesis','proposal.intuition'),
    'core_problem':('proposal.core_problem','proposal.problem','gap.methodological_deficiency.statement','gap.statement'),
    'key_novelty':('proposal.key_novelty','novelty_assessment.basis','proposal.difference_from_recent_work','novelty_vs_recent_work'),
    'method':('proposal.method','proposal.methodological_contribution'),
    'proposed_evaluation':('proposal.proposed_evaluation','proposal.validation','falsifiable_validation'),
    'falsifiable_predictions':('proposal.falsifiable_predictions','proposal.validation.falsification','falsifiable_validation.falsifiers'),
    'limitations':('proposal.limitations','proposal.risks_and_controls','main_risk'),
}

def field(report,path):
    value=report
    for part in path.split('.'):
        if not isinstance(value,dict):return None
        value=value.get(part)
    return value

def canonical(report):
    if not isinstance(report,dict):raise ValueError('Native report must be an object')
    mapped=dict(report);mapping={}
    for name in REQUIRED:
        if mapped.get(name):continue
        for path in ALIASES[name]:
            value=field(report,path)
            if value:
                mapped[name]=value;mapping[name]=path;break
    missing=[name for name in REQUIRED if not mapped.get(name)]
    if missing:raise ValueError('Substantive report content missing: '+', '.join(missing))
    if not isinstance(mapped['title'],str):raise ValueError('Report title must be text')
    return mapped,mapping

def can_normalize(native):
    try:
        report,mapping=canonical(read(native/'outputs/report.json'))
        _,literals=extract(report)
        return bool(mapping or literals)
    except (ValueError,TypeError):return False

def can_finalize(native):
    try:
        canonical(read(native/'outputs/report.json'))
        return all((native/'outputs'/name).is_file() for name in ('plan.md','gaps.md','candidates.md','scores.md'))
    except (ValueError,TypeError):return False


def finalize(native,domain,index):
    raw=native/'outputs/report.json';digest=sha(raw)
    report,mapping=canonical(read(raw))
    _,literals=extract(report)
    check=native/'delivery-validation-v10';outputs=check/'outputs';outputs.mkdir(parents=True,exist_ok=True)
    # The native validator reads the same original artifacts and a separate
    # canonical view of report.json. Original native bytes remain untouched.
    for name in ('plan.md','gaps.md','candidates.md','scores.md','papers'):
        source=native/'outputs'/name;target=outputs/name
        if not source.exists():raise ValueError('Missing native artifact: '+name)
        if not target.exists():target.symlink_to(source)
    save(outputs/'report.json',report)
    entry=load_module('isci_native_validation_v10',Path(__file__).parent/'native_delivery.py')
    config=read(native/'run_config.json')
    delivery=entry.validate_delivery(check,config)
    if delivery['status']!='passed':raise ValueError('Normalized native delivery invalid: '+safe(delivery['errors']))
    refs=[]
    for item in read(outputs/'bibliography.json',[]):
        refs.append(dict(item,reading_depth=read(native/'evidence'/f"{item['paper_id']}.json",{'source':'unknown'})))
    # Render ALL original report content; the schema mapping adds no research.
    original=read(raw)
    md='# '+report['title']+'\n\n'+render(original)
    card=dict(schema_version='research.idea_card.v1',method_id='ideascientist',domain_id=domain,
        card_id=f'ideascientist-{domain}-{index:02}',title=report['title'],idea_card_md=md,
        native_artifact=str(raw),native_sha256=digest,source_refs=refs,
        normalization_artifact=str(outputs/'report.json'),normalization_mapping=mapping,
        validation=dict(native_delivery=delivery,experiments_run=False,scientific_validity_verified=False,
                        original_report_preserved=True,model_calls_for_normalization=0))
    assert sha(raw)==digest,'Original native report changed during validation'
    save(native/'idea_card.json',card);(native/'idea_card.md').write_text(md+'\n')
    save(check/'mapping.json',dict(at=now(),source=str(raw),source_sha256=digest,
         source_fields=mapping,excluded_numeric_literals=literals,scientific_content_added=False,model_calls=0))
    save(native/'status.json',dict(state='completed',finished_at=now(),card=str(native/'idea_card.json'),
         recovery='existing_report_delivery_validation_v10',native_report_sha256=digest))
    return card
