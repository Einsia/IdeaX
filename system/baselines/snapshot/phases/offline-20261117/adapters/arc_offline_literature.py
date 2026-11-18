"""Replace research backends while retaining native ARC collection orchestration."""
from contextlib import contextmanager
from dataclasses import replace
import re
from offline_support import RawLibrary, _mod


@contextmanager
def local_backends(output):
    from researchclaw.literature import search
    from researchclaw.literature.models import Paper
    from researchclaw.web import search as web, scholar, crawler, pdf_extractor, agent
    library = RawLibrary(output)
    originals=[]
    def patch(target,name,value):
        originals.append((target,name,getattr(target,name)))
        setattr(target,name,value)
    def paper(row):
        doc=library.read(row['paper_id'])
        return Paper(paper_id=row['paper_id'],title=row['title'],
            year=int(str(row.get('date') or '0')[:4]),abstract=doc.get('abstract',''),
            venue=row.get('venue') or '',arxiv_id=row.get('arxiv') or '',
            url=row.get('source_url') or row['paper_id'],source='offline_raw_corpus')
    def search_papers(query, *, limit=20, sources=(), year_min=0, **kwargs):
        # One common collection replaces the named network backends. Native query
        # expansion, cross-query deduplication, screening and selection stay intact.
        rows=library.search(query,limit)
        return [paper(row) for row in rows if not year_min or int(str(row.get('date') or '0')[:4])>=year_min]
    def web_search(client,query,*,max_results=None,**kwargs):
        rows=library.search(query,max_results or client.max_results)
        return web.WebSearchResponse(query=query,source='offline_raw_corpus',results=[
            web.SearchResult(title=r['title'],url=r.get('source_url') or r['paper_id'],snippet=r.get('snippet',''),
                source='offline_raw_corpus') for r in rows])
    class LocalScholar(scholar.ScholarPaper):
        def to_literature_paper(self):
            return replace(super().to_literature_paper(),source='offline_raw_corpus')
    def scholar_search(client,query,*,limit=10):
        return [LocalScholar(title=p.title,year=p.year,abstract=p.abstract,url=p.url,scholar_id=p.paper_id,
            venue=p.venue,source='offline_raw_corpus') for p in search_papers(query,limit=limit)]
    def read_page(client,url):
        try:
            doc=library.read(url,max_chars=client.max_content_length)
        except _mod.CorpusError as exc:
            return crawler.CrawlResult(url=url,success=False,error=str(exc),metadata={'offline':True,'network_fallback':False})
        text=f"Offline raw corpus; read_depth={doc['read_depth']}; paper_id={doc['paper_id']}; truncated={doc['truncated']}\n\n"+doc['text']
        return crawler.CrawlResult(url=url,markdown=text,title=doc['title'],success=True,
            metadata={'offline':True,'read_depth':doc['read_depth'],'paper_id':doc['paper_id'],
                      'content_sha256':doc['content_sha256'],'truncated':doc['truncated']})
    async def crawl(client,url): return read_page(client,url)
    async def crawl_many(client,urls): return [read_page(client,url) for url in urls]
    def extract_from_url(client,url,**kwargs):
        try:
            doc=library.read(url,require_full_text=True)
        except _mod.CorpusError as exc:
            return pdf_extractor.PDFContent(path=url,error=str(exc),backend='offline_raw_corpus')
        return pdf_extractor.PDFContent(path=url,text=doc['text'],title=doc['title'],abstract=doc.get('abstract',''),
            success=True,backend='offline_raw_corpus',metadata={'offline':True,'read_depth':doc['read_depth'],
            'paper_id':doc['paper_id'],'content_sha256':doc['content_sha256']})
    patch(search,'search_papers',search_papers)
    patch(web.WebSearchClient,'search',web_search)
    patch(scholar.GoogleScholarClient,'__init__',lambda self,**kw:None)
    patch(scholar.GoogleScholarClient,'search',scholar_search)
    patch(crawler.WebCrawler,'crawl',crawl)
    patch(crawler.WebCrawler,'crawl_sync',read_page)
    patch(crawler.WebCrawler,'crawl_many',crawl_many)
    patch(pdf_extractor.PDFExtractor,'extract_from_url',extract_from_url)
    try: yield library
    finally:
        for target,name,value in reversed(originals): setattr(target,name,value)
