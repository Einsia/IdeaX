"""Repair native backward traversal and prevent short chains reaching ideation."""
import json,re
from pathlib import Path
from prompts import get_deep_judge_relevant_prompt
from utils import extract

def titles(row):return re.findall(r'(?m)^\d+\.Paper:(.*?) idea:',row.get('idea_chains',''))

def valid_chain(row,minimum,maximum):
    ts=titles(row)
    return minimum<=len(ts)<=maximum and len(set(t.casefold().strip() for t in ts))==len(ts) and all(len(row.get(k,[]))==len(ts) for k in ('ideas','experiments','entities','years'))

def require_chain(anchor,papers,minimum,maximum):
    if minimum<=len(papers)<=maximum and len(set(t.casefold().strip() for t in papers))==len(papers):return
    failure=dict(anchor=anchor,papers=papers,minimum=minimum,maximum=maximum,reason='insufficient_native_paper_chain',zero_score=False)
    Path('chain_failure.json').write_text(json.dumps(failure,ensure_ascii=False,indent=2))
    raise RuntimeError('IncompleteNativeChain: '+str(len(papers))+' unique papers; native chain must be completed before generating an idea')

async def extend_backwards(agent,anchor,references,idea_papers,idea_chain,experiments,total_entities,years):
    current_title,current_abstract=anchor.title,anchor.abstract
    references=list(references) if isinstance(references,list) else []
    attempted=set(idea_papers)
    for _ in range(40):
        if len(idea_chain)>=agent.max_chain_length:break
        cite=None
        while references:
            reference=references.pop(0)
            if not isinstance(reference,str) or reference in attempted or reference in agent.read_papers:continue
            attempted.add(reference)
            found=await agent.reader.search_async(reference,1,llm=agent.llm,publicationDate=agent.publicationData,paper_list=idea_papers,exact_title=reference)
            if not found:continue
            candidate=found[0]
            if not candidate or not candidate.article or candidate.title in idea_papers or candidate.title in agent.read_papers:continue
            response=await agent.get_openai_response_async(agent.wrap_messages(get_deep_judge_relevant_prompt(candidate.title,candidate.abstract,agent.topic)))
            if extract(response,'relevant')!='0' or len(idea_chain)<agent.min_chain_length:
                cite=candidate;break
        if cite is None:
            # Query real indexed references even when the extracted reference list
            # is empty. Never construct citation edges from topical similarity.
            cite=await agent.reader.search_related_paper_async(current_title,need_citation=False,rerank_query=f'topic: {agent.topic} Title: {current_title} Abstract: {current_abstract}',llm=agent.llm,paper_list=list(attempted|set(idea_papers)))
            if not cite:break
            if not cite.article or cite.title in idea_papers:break
            attempted.add(cite.title)
            if len(idea_chain)>=agent.min_chain_length:
                response=await agent.get_openai_response_async(agent.wrap_messages(get_deep_judge_relevant_prompt(cite.title,cite.abstract,agent.topic)))
                if extract(response,'relevant')=='0':continue
        # A found reference is read and appended before any stopping condition.
        idea,experiment,entities,raw_refs=await agent.get_article_idea_experiment_references_info(cite.article)
        if not idea or not experiment or not entities:raise RuntimeError('Native reference extraction was incomplete')
        try:references=json.loads(raw_refs)
        except (ValueError,TypeError):references=[]
        if not isinstance(references,list):references=[]
        current_title,current_abstract=cite.title,cite.abstract
        idea_papers.insert(0,cite.title);idea_chain.insert(0,idea);experiments.insert(0,experiment);total_entities.insert(0,entities);years.insert(0,cite.year)
        agent.reader._trace('native_chain_reference_appended',title=cite.title,source_url=cite.source_url,chain_length=len(idea_chain))
        if len(idea_chain)>=agent.min_chain_length and cite.citations_conut>1000:break
