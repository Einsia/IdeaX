import asyncio,json,os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from common import ROOT, REPO
sys.path.insert(0,str(REPO/'baselines/coi/source'))
from chain_integrity import extend_backwards,valid_chain,require_chain
from agents import DeepResearchAgent
from searcher import Result

class ChainRecoveryTests(unittest.TestCase):
    def agent(self,graph):
        reader=SimpleNamespace(search_async=AsyncMock(return_value=[]),search_related_paper_async=AsyncMock(return_value=graph),_trace=lambda *a,**kw:None)
        return SimpleNamespace(reader=reader,read_papers=set(),llm=None,publicationData=None,topic='topic',min_chain_length=2,max_chain_length=3,
            get_article_idea_experiment_references_info=AsyncMock(return_value=('real idea','real experiment','entities','[]')),
            get_openai_response_async=AsyncMock(return_value='<relevant>1</relevant>'),wrap_messages=lambda text:[dict(role='user',content=text)])
    def test_empty_extracted_references_still_use_real_graph_and_append(self):
        anchor=Result('anchor','abstract',{},0,2025);ref=Result('real reference','abstract',{'body':'actual'},1500,2020,'https://example.test/ref')
        agent=self.agent(ref);papers=['anchor'];ideas=['anchor idea'];exp=['anchor experiment'];entities=['anchor entities'];years=[2025]
        asyncio.run(extend_backwards(agent,anchor,[],papers,ideas,exp,entities,years))
        self.assertEqual(papers,['real reference','anchor']);self.assertEqual(years,[2020,2025]);self.assertEqual(len(ideas),2)
        agent.get_article_idea_experiment_references_info.assert_awaited_once_with(ref.article)
        self.assertFalse(agent.reader.search_related_paper_async.call_args.kwargs['need_citation'])
    def test_unresolved_titles_fall_back_to_graph_without_skipping_append(self):
        anchor=Result('anchor','',{},0,2025);ref=Result('real reference','',{'body':'actual'},1500,2020)
        agent=self.agent(ref);papers=['anchor'];ideas=['idea']
        asyncio.run(extend_backwards(agent,anchor,['unresolved title'],papers,ideas,['exp'],['entities'],[2025]))
        self.assertEqual(len(papers),2);agent.reader.search_async.assert_awaited_once()
    def test_duplicate_graph_paper_cannot_pad_chain(self):
        anchor=Result('anchor','',{'body':'actual'},1500,2025);agent=self.agent(anchor);papers=['anchor']
        asyncio.run(extend_backwards(agent,anchor,[],papers,['idea'],['exp'],['entities'],[2025]))
        self.assertEqual(papers,['anchor']);agent.get_article_idea_experiment_references_info.assert_not_awaited()
    def test_short_cached_chain_is_not_complete(self):
        row=dict(idea_chains='0.Paper:A idea:read A\n',ideas=['a'],experiments=['e'],entities=['x'],years=[2025])
        self.assertFalse(valid_chain(row,2,3))
        row.update(idea_chains='0.Paper:A idea:read A\n1.Paper:B idea:read B\n',ideas=['a','b'],experiments=['e','f'],entities=['x','y'],years=[2020,2025])
        self.assertTrue(valid_chain(row,2,3))
    def test_native_stops_before_ideation_when_both_directions_fail(self):
        previous=Path.cwd()
        with tempfile.TemporaryDirectory(dir=os.environ['IDEAX_SCRATCH']) as folder:
            try:
                os.chdir(folder);Path('logs').mkdir();agent=self.agent(None);agent.log_save_file='logs'
                anchor=Result('isolated anchor','abstract',{'body':'actual'},0,2025)
                with self.assertRaisesRegex(RuntimeError,'IncompleteNativeChain'):
                    asyncio.run(DeepResearchAgent.deep_research_paper_with_chain(agent,anchor))
                agent.get_openai_response_async.assert_not_awaited()
                failure=json.loads(Path('chain_failure.json').read_text());self.assertFalse(failure['zero_score']);self.assertEqual(failure['anchor'],'isolated anchor')
                self.assertFalse(Path('logs/deep_research_chains.json').exists())
            finally:os.chdir(previous)

if __name__=='__main__':unittest.main()
