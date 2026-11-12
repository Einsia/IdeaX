import json
import time
import asyncio
import os
from searcher import Result,SementicSearcher
from LLM import openai_llm
from prompts import *
from utils import extract
from chain_integrity import valid_chain, require_chain, extend_backwards


def get_llm(model = "gpt4o-0513"):
    return openai_llm(model)


def get_llms():
    if "MAIN_LLM_MODEL" not in os.environ or os.environ["MAIN_LLM_MODEL"] == "":
        raise ValueError("MAIN_LLM_MODEL is not set")
    if "CHEAP_LLM_MODEL" not in os.environ or os.environ["CHEAP_LLM_MODEL"] == "":
        raise ValueError("CHEAP_LLM_MODEL is not set")
    main_llm = os.environ.get("MAIN_LLM_MODEL","gpt4o-0513")
    cheap_llm= os.environ.get("CHEAP_LLM_MODEL","gpt-4o-mini")
    main_llm = get_llm(main_llm)
    cheap_llm = get_llm(cheap_llm)
    return main_llm,cheap_llm



async def judge_idea(i,j,idea0,idea1,topic,llm):
    prompt = get_judge_idea_all_prompt(idea0,idea1,topic)
    messages = [{"role":"user","content":prompt}]
    response = await llm.response_async(messages)
    novelty = extract(response,"novelty")
    relevance = extract(response,"relevance")
    significance = extract(response,"significance")
    clarity = extract(response,"clarity")
    feasibility = extract(response,"feasibility")
    effectiveness = extract(response,"effectiveness")
    return i,j,novelty,relevance,significance,clarity,feasibility,effectiveness



class ReviewAgent:
    def __init__(self,save_file = "saves/",llm = None,cheap_llm = None,publicationData = None,**kwargs) -> None:
        self.paper_save_file = os.path.join(save_file,"review_papers")
        self.log_save_file = os.path.join(save_file,"review_logs")
        if not os.path.exists(self.paper_save_file):
            os.makedirs(self.paper_save_file)
        if not os.path.exists(self.log_save_file):
            os.makedirs(self.log_save_file)
        self.llm = llm
        self.cheap_llm = cheap_llm
        self.reader = SementicSearcher(self.paper_save_file)
        self.read_papers = set()
        self.begin_time = time.time()
        self.review_suggestions = []
        self.review_idea_suggestions = []
        self.review_experiment_suggestions = []
        self.check_novel_results = []
        self.publicationData = publicationData

    def wrap_messages(self,prompt):
        return [{"role":"user","content":prompt}]

    async def get_openai_response_async(self,messages):
        return await self.llm.response_async(messages)
    
    async def get_cheap_openai_response_async(self,messages):
        return await self.cheap_llm.response_async(messages)

    async def get_search_query(self,idea,topic):
        prompt = get_review_search_related_paper_prompt(idea,topic)
        messages = self.wrap_messages(prompt)
        response = await self.get_openai_response_async(messages)
        search_query = extract(response,"queries")
        try:
            search_query = json.loads(search_query)
        except:
            search_query = []
        return search_query
    
    async def get_suggestions_from_papers(self,papers,topic,idea):
        paper_content = ""
        for i,paper in enumerate(papers):
            paper_content += f"{i}.Title: {paper.title}, Abstract: {paper.abstract}\n"

        prompt = get_review_suggestions_from_papers_prompt(idea,topic,paper_content)
        messages = self.wrap_messages(prompt)
        response = await self.get_openai_response_async(messages)
        suggestions = extract(response,"suggestions")
        print(f"successfully get suggestions from paper {paper.title}")
        return suggestions


    async def correct_source_declarations(self, idea, feedback):
        prompt = f"""You are the native ReviewAgent performing a factual provenance correction.
The following feedback is a deterministic audit of this run's actual source trace, not a new scientific proposal:
{feedback}
Original native idea:
{idea}
Return the complete corrected original idea in <final_idea>...</final_idea> and a short <source_correction>...</source_correction>.
Correct only factual declarations of what this pipeline read, what the current role received as a summary, and whether a named paper is an analyzed original or an unverified citation. Do not change the core mechanism, hypotheses, comparisons, experimental predictions, or scope. If a key comparison depends on an unread source, retain it only as explicitly unresolved and unverified; do not invent a mechanism or imply an original was checked. Preserve the Chinese original as much as possible. Distinguish the run's original-paper reads from the current stage's generated source summaries. Do not add citations or fabricate reading. Opening XML tags must begin new lines, with no preamble. Write the full corrected idea within 6500 Chinese characters."""
        response = await self.get_cheap_openai_response_async(self.wrap_messages(prompt))
        corrected = extract(response, "final_idea", hard=False)
        correction = extract(response, "source_correction", hard=False)
        if not corrected or not correction:
            raise RuntimeError("Native provenance review did not return complete corrected idea and source correction")
        with open(os.path.join(self.log_save_file,"source_declaration_correction.json"),"w") as handle:
            json.dump({"original_idea":idea,"feedback":feedback,"corrected_idea":corrected,"correction":correction},handle,ensure_ascii=False)
        import difflib
        with open(os.path.join(self.log_save_file,"source_declaration_correction.diff"),"w") as handle:
            handle.write("".join(difflib.unified_diff(idea.splitlines(True), corrected.splitlines(True),
                fromfile="native_idea_before", tofile="native_idea_after_source_review")))
        return corrected

    async def review_experiment(self,idea,experiment,entities):
        prompt = get_review_experiment_design_suggestions_prompt(idea,experiment,entities)
        from pathlib import Path
        feedback_path = Path("source_review_feedback.json")
        if feedback_path.exists():
            prompt += "\nDeterministic source audit feedback to address in this native review:\n" + feedback_path.read_text()

        messages = self.wrap_messages(prompt)
        response = await self.get_cheap_openai_response_async(messages)
        suggestions = extract(response,"suggestion")
        review_suggestion = {"idea":idea,"experiment":experiment,"suggestions":suggestions}
        self.review_experiment_suggestions.append(review_suggestion)
        with open(os.path.join(self.log_save_file,"review_experiment_suggestions.json"),"w") as f:
            json.dump(self.review_experiment_suggestions,f)
        return suggestions


class DeepResearchAgent:
    def __init__(self,save_file = "saves/",llm = None,cheap_llm=None,publicationData = None,ban_paper = [],**kwargs) -> None:
        self.paper_save_file = os.path.join(save_file,"deep_papers")
        self.log_save_file = os.path.join(save_file,"deep_logs")
        if not os.path.exists(self.paper_save_file):
            os.makedirs(self.paper_save_file)
        if not os.path.exists(self.log_save_file):
            os.makedirs(self.log_save_file)
        self.reader = SementicSearcher(save_file = self.paper_save_file,ban_paper = ban_paper)
        self.begin_time = time.time()
        self.llm = llm
        self.cheap_llm = cheap_llm
        self.read_papers = set()
        from pathlib import Path
        excluded=Path('chain_exclusions.json')
        if excluded.exists():self.read_papers.update(json.loads(excluded.read_text()))
        self.paper_storage = []
        self.paper_info_for_refine_experiment = []
        self.search_qeuries = []
        self.deep_research_chains = []
        self.deep_ideas = []
        self.check_novel_results = []
        self.score_results = []
        self.topic =None


        self.publicationData = publicationData
        self.improve_cnt = kwargs.get("improve_cnt",1)
        self.max_chain_length = kwargs.get("max_chain_length",5)
        self.min_chain_length = kwargs.get("min_chain_length",3)
        self.max_chain_numbers = kwargs.get("max_chain_numbers",10)

    def wrap_messages(self,prompt):
        return [{"role":"user","content":prompt}]

    async def get_openai_response_async(self,messages):
        return await self.llm.response_async(messages)
    
    async def get_cheap_openai_response_async(self,messages):
        return await self.cheap_llm.response_async(messages,max_tokens = 16000)

    async def get_search_query(self,topic = None,query=None):
        prompt = get_deep_search_query_prompt(topic,query)
        messages = self.wrap_messages(prompt)
        response = await self.get_openai_response_async(messages)
        search_query = extract(response,"queries")
        try:
            search_query = json.loads(search_query)
            self.search_qeuries.append({"query":query,"search_query":search_query})
            with open(os.path.join(self.log_save_file,"search_queries.json"),"w") as f:
                json.dump(self.search_qeuries,f)
        except:
            search_query = [query]
        return search_query

    async def generate_idea_with_chain(self,topic,anchor_paper_path = None):
        self.topic = topic
        # Restore a completed same-task native chain before repeating anchor
        # search; source selection must not change during later-stage recovery.
        from pathlib import Path
        import re
        chain_file = Path(self.log_save_file) / "deep_research_chains.json"
        saved_chain = None
        if chain_file.exists():
            prior_chains = json.loads(chain_file.read_text())
            saved_chain = next((row for row in reversed(prior_chains) if row.get("topic") == topic and valid_chain(row,self.min_chain_length,self.max_chain_length)), None)
        if saved_chain:
            titles = re.findall(r"(?m)^\d+\.Paper:(.*?) idea:", saved_chain["idea_chains"])
            title = saved_chain.get("anchor_title") or titles[-1]
            papers = [Result(title, "", {}, 0, None)]
            print("completed_native_chain_selected_before_retrieval:", title, flush=True)
        elif anchor_paper_path:
            article = self.reader.read_arxiv_from_path(anchor_paper_path)
            title,abstract,pub_data = article["title"],article["abstract"],article["pub_date"]
            paper = Result(title,abstract,article,0,pub_data)
            papers = [paper]
        else:
            search_query = await self.get_search_query(topic=topic)
            papers = []
            for query in search_query:
                failed_query = []
                current_papers = []
                cnt = 0
                while len(current_papers) == 0 and cnt < 10:
                    paper = await self.reader.search_async(query,1,paper_list=self.read_papers,llm=self.llm,rerank_query=f"{topic}",publicationDate=self.publicationData)
                    if paper and len(paper) > 0 and paper[0]:
                        candidate = paper[0]
                        gate_prompt = f"""Evaluate only whether this real retrieved source can anchor the specified scientific task.
Scientific task: {topic}
Actual retrieved paper title: {candidate.title}
Actual retrieved abstract: {candidate.abstract}
The anchor must directly study the research object or a core problem in the domain and scope explicitly stated in the scientific task above. A paper that merely shares generic terminology or applies an unrelated mechanism to an unrelated task is insufficient as the sole anchor. Such work may be a later cross-domain mechanism source, with explicit transfer assumptions. Do not infer relevance from the search query; use the actual source title and abstract. Output only <relevant>1</relevant> or <relevant>0</relevant> and a short <reason>source-grounded explanation</reason>."""
                        gate_response = await self.get_openai_response_async(self.wrap_messages(gate_prompt))
                        accepted = extract(gate_response, "relevant") == "1"
                        self.reader._trace("native_anchor_relevance_check", title=candidate.title,
                            source_url=candidate.source_url, accepted=accepted,
                            reason=extract(gate_response, "reason"))
                        if not accepted:
                            self.read_papers.add(candidate.title)
                            failed_query.append(query + " [Actual retrieved source rejected as task anchor: " + candidate.title + "]")
                            rewrite = get_deep_rewrite_query_prompt(failed_query,topic)
                            rewrite += "\nKeep the research object and scope from the scientific task explicit. Return a concise English academic query; do not broaden to an unrelated application just to obtain a result. Do not name a paper unless its title is known."
                            revised = await self.get_openai_response_async(self.wrap_messages(rewrite))
                            query = extract(revised, "query")
                            print("Task anchor rejected by native source relevance check; revised query:", query, flush=True)
                            cnt += 1
                            continue
                        self.read_papers.add(paper[0].title)
                        current_papers.append(paper[0])
                    else:
                        failed_query.append(query)
                        prompt = get_deep_rewrite_query_prompt(failed_query,topic)
                        messages = self.wrap_messages(prompt)
                        new_query = await self.get_openai_response_async(messages)
                        new_query = extract(new_query,"query")
                        print(f"Failed to search papers for {query}, regenerating query {new_query} to search papers.")
                        query = new_query
                    cnt += 1
                papers.extend(current_papers)
                if len(papers) >= self.max_chain_numbers:
                    break

            if len(papers) == 0:
                print(f"failed to generate idea {topic}")
                return None,None,None,None,None,None,None,None,None

        tasks = [self.deep_research_paper_with_chain(paper) for paper in papers]
        results = await asyncio.gather(*tasks)
        results = [result for result in results if result]
        if len(results) ==0:
            print(f"failed to generate idea {topic}")
            return None,None,None,None,None,None,None,None,None

        ideas,idea_chains,experiments,entities,trends,futures,humans,years = [[result[i] for result in results] for i in range(8)]

        tasks = []
        for i,idea_1 in enumerate(ideas):
            for j,idea_2 in enumerate(ideas):
                if i != j:
                    tasks.append(judge_idea(i,j,idea_1,idea_2,topic,self.llm))
        results = await asyncio.gather(*tasks)
        elo_scores = [0 for _ in range(len(ideas))]
        elo_selected = 0
        def change_winner_to_score(winner,score_1,score_2):
            try:
                winner = int(winner)
            except:
                return score_1+0.5,score_2+0.5
            if winner == 0:
                return score_1+1,score_2
            if winner == 2:
                return score_1+0.5,score_2+0.5
            return score_1,score_2+1
        for result in results:
            i,j,novelty,relevance,significance,clarity,feasibility,effectiveness = result
            for dimension in [novelty,relevance,significance,clarity,feasibility,effectiveness]:
                elo_scores[i],elo_scores[j] = change_winner_to_score(dimension,elo_scores[i],elo_scores[j])
            print(f"i:{i},j:{j},novelty:{novelty},relevance:{relevance},significance:{significance},clarity:{clarity},feasibility:{feasibility},effectiveness:{effectiveness}")
        print(elo_scores)
        try:
            elo_selected = elo_scores.index(max(elo_scores))
        except:
            elo_selected = 0
        
        idea,experiment,entities,idea_chain,trend,future,human,year = ideas[elo_selected],experiments[elo_selected],entities[elo_selected],idea_chains[elo_selected],trends[elo_selected],futures[elo_selected],humans[elo_selected],years[elo_selected]

        with open(os.path.join(self.log_save_file,"deep_result.json"),"w") as f:
            json.dump({"ideas":ideas,"experiments":experiments,"entities":entities},f)

        print(f"successfully generated idea")
        return idea,experiment,entities,idea_chain,ideas,trend,future,human,year
    
    async def get_paper_idea_experiment_references_info(self,paper:Result):
        article = paper.article
        if not article:
            return None
        paper_content = self.reader.read_paper_content(article)
        prompt = get_deep_reference_prompt(paper_content,self.topic)
        messages = self.wrap_messages(prompt)
        response = await self.get_cheap_openai_response_async(messages)
        entities = extract(response,"entities")
        idea = extract(response,"idea")
        experiment = extract(response,"experiment")
        references = extract(response,"references")
        return idea,experiment,entities,references,paper.title

    async def get_article_idea_experiment_references_info(self,article):
        paper_content = self.reader.read_paper_content_with_ref(article)
        prompt = get_deep_reference_prompt(paper_content,self.topic)
        messages = self.wrap_messages(prompt)
        response = await self.get_cheap_openai_response_async(messages)
        entities = extract(response,"entities")
        idea = extract(response,"idea")
        experiment = extract(response,"experiment")
        references = extract(response,"references")
        return idea,experiment,entities,references

    
    async def get_paper_info_for_refine_experiment(self,paper,experiment,suggestions):
        article = paper.article
        if not article:
            return {"title":paper.title,"info":None}
        paper_content = self.reader.read_paper_content_with_ref(article)
        prompt = get_deep_paper_info_prompt_for_refine_experiment(paper_content,experiment,suggestions)
        messages = self.wrap_messages(prompt)
        response = await self.get_cheap_openai_response_async(messages)
        info = extract(response,"info")
        return {"title":paper.title,"info":info}

    
    async def deep_research_paper_with_chain(self,paper:Result): 
        print(f"begin to deep research paper {paper.title}")
        from pathlib import Path
        chain_path = Path(self.log_save_file) / "deep_research_chains.json"
        cached_chain = None
        if chain_path.exists():
            previous = json.loads(chain_path.read_text())
            cached_chain = next((row for row in reversed(previous) if row.get("topic") == self.topic
                and ("Paper:" + paper.title + " idea:") in row.get("idea_chains", "") and valid_chain(row,self.min_chain_length,self.max_chain_length)), None)
        if cached_chain:
            idea_chains = cached_chain["idea_chains"]
            idea_chain = cached_chain["ideas"]
            experiments = cached_chain["experiments"]
            total_entities = cached_chain["entities"]
            years = cached_chain["years"]
            trend = cached_chain["trend"]
            print("completed_native_literature_chain_restored:", paper.title, flush=True)
        else:
            article = paper.article
            if not article:
                print(f"failed to deep research paper {paper.title}")
                return None
            idea_chain,idea_papers,experiments,total_entities,years = [],[],[],[],[]
            idea,experiment,entities,references = await self.get_article_idea_experiment_references_info(article)
            try:
                references = json.loads(references)
            except:
                references = []
            total_entities.append(entities)
            idea_chain.append(idea)
            idea_papers.append(paper.title)
            experiments.append(experiment)
            years.append(paper.year)

            current_title = paper.title
            current_abstract = paper.abstract

            # Forward search: search future papers (citations)
            while len(idea_chain)<self.max_chain_length:
                rerank_query = f"{self.topic} {current_title} {current_abstract}"
                citation_paper = await self.reader.search_related_paper_async(current_title,need_reference=False,rerank_query=rerank_query,llm=self.llm,paper_list=idea_papers)
                if not citation_paper:
                    break

                title = citation_paper.title
                prompt = get_deep_judge_relevant_prompt(citation_paper.title,citation_paper.abstract,self.topic)
                messages = self.wrap_messages(prompt)
                response = await self.get_openai_response_async(messages)
                relevant = extract(response,"relevant")
                if relevant != "0":
                    result = await self.get_paper_idea_experiment_references_info(citation_paper)
                    if not result:
                        break
                    idea,experiment,entities,_,_ = result
                    idea_chain.append(idea)
                    experiments.append(experiment)
                    total_entities.append(entities)
                    idea_papers.append(citation_paper.title)
                    years.append(citation_paper.year)
                    current_title = citation_paper.title
                    current_abstract = citation_paper.abstract
                else:
                    print(f"the paper {title} is not relevant to the topic")
                    break

            # Continue the original chain through actual references.
            await extend_backwards(self,paper,references,idea_papers,idea_chain,experiments,total_entities,years)
            require_chain(paper.title,idea_papers,self.min_chain_length,self.max_chain_length)

            idea_chains = ""
            for i,idea,title in zip(range(len(idea_chain)),idea_chain,idea_papers):
                idea_chains += f"{i}.Paper:{title} idea:{idea}\n \n"
        
            prompt = get_deep_trend_idea_chains_prompt(idea_chains,entities,self.topic)
            messages = self.wrap_messages(prompt)
            response = await self.get_openai_response_async(messages)
            trend = extract(response,"trend")

            self.deep_research_chains.append({"anchor_title":paper.title,"idea_chains":idea_chains,"trend":trend,"topic":self.topic,"ideas":idea_chain,"experiments":experiments,"entities":total_entities,"years":years})
            with open(os.path.join(self.log_save_file,"deep_research_chains.json"),"w") as f:
                json.dump(self.deep_research_chains,f)
        prompt = f"""The current research topic is: {self.topic}. Please help me summarize and refine the following entities by merging, simplifying, or deleting them : {total_entities}
    Please output strictly in the following format: 
    <entities> {{cleaned entities}}</entities>
"""
        messages = self.wrap_messages(prompt)
        response = await self.get_openai_response_async(messages)
        total_entities = extract(response,"entities")
        bad_case = []
        novel = False
        print(f"begin to check novel")
        novelty_attempts = 0
        while not novel:
            novelty_attempts += 1
            if novelty_attempts > int(os.environ.get("COI_MAX_NOVELTY_ATTEMPTS", "5")):
                raise RuntimeError("Novelty screening rejected all candidates within the configured retry budget")
            future = None
            human = None
            prompt = get_deep_generate_future_direciton_prompt(idea_chain,trend,self.topic,total_entities)
            revision_path = Path("within_run_revision.json")
            if revision_path.exists():
                revision = json.loads(revision_path.read_text())
                prompt += "\nWithin-run native self-review feedback (contains only this run's own prior direction; no other run's candidate):\n" + json.dumps(revision,ensure_ascii=False)
                prompt += "\nReconstruct one materially different core memory mechanism using the same original source chain and public task. Do not merely change the loss, coefficient, optimizer, query scope or parameter subset of the prior direction. Re-examine the problem and storage/read/write/forgetting rule. Do not reference another run. Return only the current native stage fields; retain causal feedback, falsifiable tests, source caveats and all task requirements."

            messages = self.wrap_messages(prompt)
            response = await self.get_openai_response_async(messages)
            future = extract(response,"future")
            human = extract(response,"human")
            

            prompt = get_deep_generate_idea_prompt(idea_chains,trend,self.topic,total_entities,future,bad_case)
            revision_path = Path("within_run_revision.json")
            if revision_path.exists():
                revision = json.loads(revision_path.read_text())
                prompt += "\nWithin-run native self-review feedback (contains only this run's own prior direction; no other run's candidate):\n" + json.dumps(revision,ensure_ascii=False)
                prompt += "\nReconstruct one materially different core memory mechanism using the same original source chain and public task. Do not merely change the loss, coefficient, optimizer, query scope or parameter subset of the prior direction. Re-examine the problem and storage/read/write/forgetting rule. Do not reference another run. Return only the current native stage fields; retain causal feedback, falsifiable tests, source caveats and all task requirements."

            messages = self.wrap_messages(prompt)
            response = await self.get_openai_response_async(messages)
            method = extract(response,"method")
            novelty = extract(response,"novelty")
            motivation = extract(response,"motivation")
            idea = {"motivation":motivation,"novelty":novelty,"method":method}
            prompt = get_deep_final_idea_prompt(idea_chains,trend,idea,self.topic)
            messages = self.wrap_messages(prompt)
            response = await self.get_openai_response_async(messages)
            final_idea = extract(response,"final_idea")
            novel = True
            novel,similar_paper,summary = await self.check_novel(final_idea)
            if not novel:
                try:
                    bad_case.append([similar_paper,summary])
                except:
                    pass
                print(f"failed to check novel")

        print(f"successfully check novel")

        idea = final_idea
        self.deep_ideas.append(idea)

        with open(os.path.join(self.log_save_file,"deep_ideas.json"),"w") as f:
            json.dump(self.deep_ideas,f)
        print(f"successfully deep research paper {paper.title}")
        # Match generate_idea_with_chain's tuple contract: idea, chain,
        # experiments, entities, trend, future, human, years.
        return idea,idea_chains,experiments,total_entities,trend,future,human,years
    
    async def check_novel(self,idea):
        search_query = await self.get_check_novel_search_query(idea)
        papers = []
        checked_papers = []
        for query in search_query:
            search_papers = await self.reader.search_async(query,5,paper_list=checked_papers,llm=self.llm,rerank_query= f"{query}",publicationDate=self.publicationData,need_download=False)
            for search_paper in search_papers:
                if search_paper.title not in checked_papers:
                    papers.append(search_paper)
                    checked_papers.append(search_paper.title)

        if len(papers) == 0:
            return True,None,""
        else:
            prompt = get_deep_check_idea_novel_prompt(idea,papers)
            messages = self.wrap_messages(prompt)
            response = await self.get_cheap_openai_response_async(messages)
            similar = extract(response,"similar")
            summary = extract(response,"summary")
            novel = True if similar != "1" else False
            similar_paper = None
            try:
                similar_paper_id = extract(response,"similar_paper_id")
                similar_paper_id = int(similar_paper_id) if similar_paper_id else 0
                similar_paper  = papers[similar_paper_id]
            except:
                pass
            return novel,similar_paper,summary
    

    async def refine_experiment(self,experiment,suggestions,entities):
        prompt = get_deep_refine_experiment_search_query_prompt(experiment,suggestions)
        messages = self.wrap_messages(prompt)
        response = await self.get_openai_response_async(messages)
        query = extract(response,"query")
        paper_infos = None
        papers = []
        if query:
            search_papers = await self.reader.search_async(query,2,publicationDate=self.publicationData)
            if len(search_papers) > 0:
                for search_paper in search_papers:
                    if search_paper and search_paper.title not in self.read_papers:
                        papers.append(search_paper)
                        self.read_papers.add(search_paper.title)

            tasks = [self.get_paper_info_for_refine_experiment(paper,experiment,suggestions) for paper in papers if isinstance(paper,Result)]
            if len(tasks) > 0:
                results = await asyncio.gather(*tasks)
                paper_infos = results
                self.paper_info_for_refine_experiment.append({"experiment":experiment,"suggestions":suggestions,"paper_infos":paper_infos})
                with open(os.path.join(self.log_save_file,"paper_info_for_refine_experiment.json"),"w") as f:
                    json.dump(self.paper_info_for_refine_experiment,f)

        prompt = get_deep_refine_experiment_prompt(experiment,suggestions,paper_infos,entities)
        messages = self.wrap_messages(prompt)
        response = await self.get_openai_response_async(messages)
        experiment = extract(response,"experiment")
        return experiment
        
    
    async def generate_experiment(self,idea,experiments,entities):
        print(f"begin to generate experiment")
        prompt = get_deep_generate_experiment_prompt(idea,experiments,entities)
        messages = self.wrap_messages(prompt)
        response = await self.get_openai_response_async(messages)
        experiment = extract(response,"experiment")
        print(f"successfully generated experiment")
        return experiment

    async def improve_experiment(self,review_agent:ReviewAgent,idea,experiment,entities):
        cnt = 0
        experiments = [experiment]
        with open(os.path.join(self.log_save_file,"experiments.json"),"w") as f:
            json.dump(experiments,f)
        while cnt < self.improve_cnt:
            print(f"begin to improve experiment {cnt}")
            suggestion = await review_agent.review_experiment(idea,experiment,entities)
            if not suggestion:
                break
            experiment = await self.refine_experiment(experiment,suggestion,entities)
            print(f"successfully improved experiment {cnt}")
            experiments.append(experiment)
            with open(os.path.join(self.log_save_file,"experiments.json"),"w") as f:
                json.dump(experiments,f)
            cnt += 1
        return experiment 
    
    async def get_check_novel_search_query(self,idea):
        prompt = get_deep_check_idea_novel_search_query_prompt(idea,self.topic)
        messages = self.wrap_messages(prompt)
        response = await self.get_openai_response_async(messages)
        search_query = extract(response,"queries")
        try:
            search_query = json.loads(search_query)
            self.search_qeuries.append({"query":idea,"search_query":search_query})
            with open(os.path.join(self.log_save_file,"search_queries.json"),"w") as f:
                json.dump(self.search_qeuries,f)
        except:
            search_query = [idea]
        return search_query



if __name__ == "__main__":
    topic = ""

    publicationData=":2022-12-01"
    review_agent = ReviewAgent()
    deep_research_agent = DeepResearchAgent()

    print(f"begin to generate idea and experiment of topic {topic}")
    idea,related_experiments,entities,idea_chain,ideas,trend,future,human,year=  asyncio.run(deep_research_agent.generate_idea_with_chain(topic))
    experiment = asyncio.run(deep_research_agent.generate_experiment(idea,related_experiments,entities))
    experiment = asyncio.run(deep_research_agent.improve_experiment(review_agent,idea,experiment,entities))
    print(f"succeed to generate idea and experiment of topic {topic}")
    res = {"idea":idea,"experiment":experiment,"related_experiments":related_experiments,"entities":entities,"idea_chain":idea_chain,"ideas":ideas,"trend":trend,"future":future,"year":year,"human":human}
    with open("result.json","w") as f:
        json.dump(res,f)

