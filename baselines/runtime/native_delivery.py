"""Same delivery checks, with numeric code/range literals excluded from citations."""
import json
from pathlib import Path
import requests
from common import save,sha
from citations import extract
from validation_metadata import resolve


def validate_delivery(run_dir,config):
    out=Path(run_dir)/'outputs'
    required=('plan.md','gaps.md','candidates.md','scores.md','report.json')
    missing=[name for name in required if not (out/name).is_file() or (out/name).stat().st_size<20]
    errors=['Missing/empty artifact: '+name for name in missing];report={}
    if 'report.json' not in missing:
        try:report=json.loads((out/'report.json').read_text())
        except (ValueError,OSError) as exc:errors.append('Invalid report JSON: '+str(exc))
    if not isinstance(report,dict):errors.append('Report must be an object');report={}
    for name in ('title','one_sentence_thesis','core_problem','key_novelty','method','proposed_evaluation','falsifiable_predictions','limitations'):
        if not report.get(name):errors.append('Report missing '+name)
    citations,literals=extract(report)
    if not citations:errors.append('No numeric vault citations in the report')
    bibliography=[]
    for pid in citations:
        digest=out/'papers'/f'{pid}.md'
        if not digest.is_file() or digest.stat().st_size<20:errors.append(f'Citation {pid} has no nonempty reader digest')
        item=resolve(pid,config,run_dir)
        if item is None:errors.append(f'Citation {pid} does not exist in the vault');continue
        if not item.get('date') or item['date'][:4]>=config['cutoff_date'][:4]:errors.append(f'Citation {pid} violates the cutoff')
        bibliography.append({k:item.get(k) for k in ('paper_id','title','date','arxiv_id','url')})
    save(out/'bibliography.json',bibliography)
    result=dict(status='passed' if not errors else 'incomplete',errors=errors,title=report.get('title'),citations=citations,
        reader_digests=len(list((out/'papers').glob('*.md'))),evidence_source=config['reader_source'],
        experiments_run=False,scientific_validity_verified=False,
        report_sha256=sha(out/'report.json') if (out/'report.json').is_file() else None,
        excluded_numeric_literals=literals,validator_revision='citation-context-v10-program-array-literals')
    save(Path(run_dir)/'delivery.json',result);return result
