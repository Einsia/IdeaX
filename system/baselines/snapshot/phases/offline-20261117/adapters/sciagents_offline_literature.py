"""Raw-only tool backends for the separately reported original-graph transfer."""
import json
from offline_support import RawLibrary,PHASE


def sciagents_environment_text():
    """Describe only interfaces actually available to the native AutoGen agents."""
    return (PHASE/'protocol/offline_environment.txt').read_text().strip() + '''

SciAgents local literature interface: use the native rate_novelty_feasibility tool to invoke the native novelty review subchat. Its response_to_query tool searches the common frozen raw-paper corpus locally, and its read_local_paper tool reads the original local text by returned local_read_id. Both are offline; neither calls public Semantic Scholar. The result distinguishes original full text, abstract, metadata, and missing text. The outer agents have the native generate_path and rate_novelty_feasibility tools; shell/CLI execution is not provided. Public URLs are provenance labels, not instructions to browse. The published graph is fixed native prior knowledge and is separate from retrieved raw literature.
'''


def bind_literature(namespace, output):
    library=RawLibrary(output)
    calls=0
    def response_to_query(query):
        nonlocal calls
        calls+=1
        rows=library.search(str(query).replace('+',' '),limit=10)
        papers=[]
        for row in rows:
            paper=library.read(row['paper_id'],max_chars=1)
            papers.append({'paperId':paper['paper_id'],'title':paper['title'],'abstract':paper['abstract'],
                           'url':paper.get('source_url'),'openAccessPdf':None,'read_depth':'abstract',
                           'full_text_available':paper['full_text_available'],'local_read_id':paper['paper_id'],
                           'source':'common_frozen_raw_corpus','corpus_raw_record_sha256':paper['raw_record_sha256']})
        result={'data':papers,'offline':True,'network_fallback':False,
                'retrieval_adaptation':'Original response_to_query tool backed by shared raw BM25; not live Semantic Scholar relevance.'}
        from pathlib import Path
        target=Path(output)/'literature_requests'/(f'{calls:04d}-offline.json')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps({'query':query,'result':result,'source':'common_frozen_raw_corpus','public_network':False},ensure_ascii=False,indent=2)+'\n')
        return result
    namespace['novelty_admin']._function_map['response_to_query']=response_to_query
    namespace['response_to_query']=response_to_query
    # Keep original tool names, argument schemas, routing and prompts. Correct only
    # transport/source descriptions so they match the actual offline execution path.
    descriptions={
        'response_to_query':'Search academic papers in the common frozen local raw corpus. Supply relevant keywords separated by +. Returns original abstracts, local_read_id and provenance; no public network or live Semantic Scholar request.',
        'rate_novelty_feasibility':'Use the original native novelty/feasibility subchat to review the hypothesis against the common frozen local raw corpus. That subchat uses local response_to_query and read_local_paper tools and returns its native analysis and 1-to-10 ratings. No public network or live Semantic Scholar access is used.',
    }
    for name in ('planner','assistant','novelty_assistant'):
        agent=namespace[name]
        for tool in list(agent.llm_config.get('tools',[])):
            function=tool.get('function',{})
            if function.get('name') in descriptions:
                updated=json.loads(json.dumps(tool));updated['function']['description']=descriptions[function['name']]
                agent.update_tool_signature(updated,is_remove=False)
    def read_local_paper(paper_id: str) -> str:
        """Read original local full text or abstract by ID, with explicit read depth and provenance."""
        return json.dumps(library.read(paper_id),ensure_ascii=False)
    namespace['novelty_admin'].register_for_execution(name='read_local_paper')(read_local_paper)
    namespace['novelty_assistant'].register_for_llm(name='read_local_paper',description='Read an original paper from the same frozen local raw library by local_read_id. Reports full_text versus abstract and missing text; never uses public network.')(read_local_paper)
    return namespace
