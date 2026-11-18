"""Raw slot scores and descriptive summaries partitioned by shared material version."""
import csv
import json
import statistics
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
REPORTS=ROOT/'reports'
sys.path.insert(0,str(ROOT/'adapters'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import read,save,now
from material_versions_scoped import generation_material, TRANSFER, MATCHED, CYCLE, DEFAULT
METHODS=('autoresearchclaw','dr_claw','researchagent','cycleresearcher','sciagents','ai_researcher','deepscientist')
V1='offline-common-corpus-20261117-v1'


def scope_matches(generation, *sources):
    return all(not source or source.get('comparison_scope', DEFAULT)==generation['comparison_scope'] for source in sources)

def material_matches(generation, sidecar, result):
    inferred = sidecar.get('data_version', result.get('data_version', V1))
    if inferred != generation['data_version']:
        return False
    if not scope_matches(generation,sidecar,result):
        return False
    return all(source.get(key, generation[key]) == generation[key]
               for source in (sidecar, result)
               for key in ('data_version', 'corpus_id', 'corpus_sha256'))


def summarize_rows(rows):
    summary=[]
    keys=sorted({(r['method'],r['data_version'],r['corpus_id'],r['comparison_scope']) for r in rows})
    for method,version,corpus_id,scope in keys:
        members=[r for r in rows if (r['method'],r['data_version'],r['corpus_id'],r['comparison_scope'])==(method,version,corpus_id,scope)]
        record={'method':method,'data_version':version,'corpus_id':corpus_id,'comparison_scope':scope,
                'expected_slots':1 if scope==TRANSFER else 190,'slots_with_this_material_version':len(members),
                'accepted':sum(r['generation_status'] in ('success','completed') for r in members),
                'native_failures':sum(r['generation_status']=='native_failure' for r in members),
                'infrastructure_failures':sum(r['generation_status']=='infrastructure_failure' for r in members),
                'mixed_material_versions_pooled':False,'mixed_comparison_scopes_pooled':False}
        for dim in ('C','I','S','Novelty'):
            vals=[r[dim] for r in members if isinstance(r.get(dim),(int,float))]
            complete=len(members)==190 and len(vals)==190
            record[dim]={'scored':len(vals),'complete':complete,'full_190_mean':statistics.mean(vals) if complete else None,
                         'available_mean_diagnostic_only':statistics.mean(vals) if vals else None}
        summary.append(record)
    return summary


def main(emit=True):
    REPORTS.mkdir(parents=True,exist_ok=True)
    domains=read(ROOT/'inputs/domains.json');rows=[];registry=read(ROOT/'state/methods.json');jobs=read(ROOT/'state/campaign.json',{}).get('jobs',{})
    for method in METHODS:
        for d in domains:
            novelty_root=ROOT/'evaluations'/method/d['id']/'novelty'
            novelty_result=read(novelty_root/'result.json',{})
            novelty=novelty_result.get('scores',{})
            novelty_material=read(novelty_root/'evaluation_material_version.json',{})
            for index in range(1,6):
                slot=f'slot-{index:02}';source=ROOT/'runs'/method/d['id']/slot;target=ROOT/'evaluations'/method/d['id']/slot
                material=generation_material(source);scope=material['comparison_scope']
                if scope==TRANSFER:
                    target=ROOT/'evaluations-transfer'/TRANSFER/method/d['id']/slot
                g=read(source/'result.json',{});c=read(target/'result.json',{});idea_id=f'{method}-{d["id"]}-{slot}';n=novelty.get(idea_id,{}) if scope!=TRANSFER else {}
                evaluation=read(target/'evaluation_material_version.json',{})
                version=material['data_version'];eval_version=evaluation.get('data_version',c.get('data_version',V1))
                novelty_version=novelty_material.get('data_version',novelty_result.get('data_version',V1))
                card_matches=material_matches(material,evaluation,c)
                novelty_matches=material_matches(material,novelty_material,novelty_result)
                job=jobs.get(f'{method}__{d["id"]}__{index:02}__generation',{});receipt_status=g.get('status')
                current_status=job.get('status',receipt_status or ('unsupported' if registry[method]['status']=='unsupported' else 'pending'))
                rows.append({'method':method,'data_version':version,'corpus_id':material['corpus_id'],
                    'evaluation_data_version':eval_version if c else None,'novelty_data_version':novelty_version if n else None,
                    'material_version_mismatch':bool((c and not card_matches) or (n and not novelty_matches)),
                    'comparison_scope':scope,
                    'evaluation_comparison_scope':evaluation.get('comparison_scope',c.get('comparison_scope')) if c else None,
                    'evaluation_result':str(target/'result.json'),
                    'original_graph_transfer_separate':scope==TRANSFER,
                    'scope_mismatch':bool((c and not scope_matches(material,evaluation,c)) or (n and not scope_matches(material,novelty_material,novelty_result))),
                    'domain':d['id'],'slot':index,'generation_status':current_status,'saved_receipt_status':receipt_status,
                    'prior_receipt_superseded_by_live_process':current_status=='running' and receipt_status in ('infrastructure_failure','adapter_failure'),
                    'C':c.get('C') if card_matches else None,'I':c.get('I') if card_matches else None,'S':c.get('S') if card_matches else None,
                    'Novelty':n.get('normalized_5') if novelty_matches else None,'Novelty_raw_100':n.get('raw_100') if novelty_matches else None,
                    'terminal_reason':None if current_status=='running' else g.get('terminal_reason'),'proposal_result':str(source/'result.json')})
    summary=summarize_rows(rows)
    save(REPORTS/'scores.json',{'at':now(),'protocol':'existing Reviewer C/I/S plus per-system five-card Novelty panel; one Astra/xhigh pass',
        'missing_policy':'Native/input/infra failures remain separate; missing never imputed zero. Full190-slot means require all scores under one material version. No post-score selection.',
        'material_policy':'Generation and evaluation material identities and comparison scopes must match. Different material versions and scopes are never pooled. Original graph transfer scores are read only from evaluations-transfer and remain separate.',
        'summary':summary,'rows':rows})
    with (REPORTS/'scores.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    if emit:print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
