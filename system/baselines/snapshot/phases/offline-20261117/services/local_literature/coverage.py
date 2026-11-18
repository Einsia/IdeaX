"""Audit source-index coverage and literal raw-query hits without model inference."""
from pathlib import Path
import ast,datetime,hashlib,json,sys
from cli import Corpus
ROOT=Path(__file__).resolve().parents[2]
domains=json.loads((ROOT/'inputs/domains.json').read_text())
source=ROOT.parents[1]/'adapters/researchagent.py'
tree=ast.parse(source.read_text());queries=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='QUERIES' for x in n.targets))
c=Corpus(ROOT/'inputs/corpus/corpus.sqlite');rows=[]
for d in domains:
    ids=[v['id'] for v in d.get('litgraph_support',{}).get('subdomains',[])] or [d['id']]
    placeholders=','.join('?' for _ in ids)
    papers=c.db.execute('SELECT DISTINCT p.paper_id,length(p.abstract)>0,p.full_text IS NOT NULL,p.has_insights,p.same_source_fulltext FROM domain_papers d JOIN papers p USING(paper_id) WHERE d.domain_id IN ('+placeholders+')',ids).fetchall()
    count=len(papers);abstracts=sum(x[1] for x in papers);full=sum(x[2] for x in papers);cards=sum(x[3] for x in papers);strict=sum(x[4] for x in papers)
    q=queries[d['id']];hits=c.search(q,limit=1,mode='all')['total'];wide=c.search(q,limit=1,mode='any')['total']
    rows.append({'domain_id':d['id'],'source_domain_ids':ids,'papers':count,'with_abstract':abstracts,'with_full_text':full,'with_insights':cards,'same_source_fulltext':strict,'missing_full_text':count-full,'source_domain_labels_origin':'existing_frozen_InsightPro_domain_papers_index_not_new_model_inference_or_author_tags','composite_union_deduplicated':len(ids)>1,'raw_query':q,'literal_all_term_hits':hits,'literal_any_term_hits':wide,'query_hit_caveat':'Lexical counts are retrieval reachability, not validated semantic topic coverage.'})
c.close()
report={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'corpus_id':json.loads((ROOT/'inputs/corpus/manifest.json').read_text())['corpus_id'],'coverage_basis':'Frozen historical InsightPro taxonomy; composite benchmark domains use only their already-frozen subdomain IDs, deduplicated by paper_id. These labels are not original author metadata and do not alter raw ranking.','domain_count':len(rows),'domains_with_source_mapped_papers':sum(x['papers']>0 for x in rows),'domains_with_some_full_text':sum(x['with_full_text']>0 for x in rows),'minimum_full_text_per_domain':min(x['with_full_text'] for x in rows),'maximum_full_text_per_domain':max(x['with_full_text'] for x in rows),'network_calls':0,'model_calls':0,'domains':rows}
(ROOT/'inputs/corpus/coverage_38_domains.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
lines=['# Frozen local corpus coverage','',report['coverage_basis'],'','Counts overlap across domains; they must not be summed as unique papers. Original metadata/abstracts and available text are in the broad main scope. The strict subset is reported separately.','','|Domain|Papers|Abstracts|Full texts|Missing full text|Strict paired subset|','|---|---:|---:|---:|---:|---:|']
for x in rows:lines.append(f"|{x['domain_id']}|{x['papers']}|{x['with_abstract']}|{x['with_full_text']}|{x['missing_full_text']}|{x['same_source_fulltext']}|")
(ROOT/'reports/local_corpus_coverage.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='domains'},indent=2));print('efficiency',next(x for x in rows if x['domain_id'].startswith('efficient_inference')))
