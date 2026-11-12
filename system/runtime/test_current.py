"""Offline regression tests for phase barriers, ownership and frozen exports."""
import copy
import tempfile
import unittest
from unittest.mock import patch
import os
from pathlib import Path
import single
import light
import cli
from common import *


def idea(n):
    return dict(title=f'idea {n}',problem='domain-P001: an important problem',mechanism='domain-I001: mechanism',
        previous_work=[dict(title=f'paper {j}',url=f'https://example.com/{j}',read_depth='abstract',source_location='abstract',overlap='x',difference='y') for j in range(3)],
        novelty_check=dict(search_queries=['a','b','c'],closest_work='a',already_done_test='b',remaining_contribution='c',unresolved_risks=[]),
        experiment='Future distinguishing observation',failure_conditions='Counterexample',scientific_potential='Conditional paper potential')


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ['IDEAX_SCRATCH']);self.root=Path(self.temp.name)
        # Source-evidence validation is tested separately in test_conditions.
        self.source_check=patch.object(single,'check_sources',return_value=[]);self.source_check.start()
        self.addCleanup(self.source_check.stop)
        self.pool=[dict(card_id=f'c-{a*5+i:03d}',author=author,idea=idea(a*5+i)) for a,author in enumerate(AUTHORS) for i in range(1,6)]
    def tearDown(self): self.temp.cleanup()
    def response(self):
        return dict(author=AUTHORS[0],responses=[dict(critic=a,response='Reasoned response') for a in AUTHORS[1:]],
            decisions=[dict(card_id=c['card_id'],action='retain',reason='Retained with evidence',idea=c['idea']) for c in self.pool[:5]])
    def test_new_schema_without_old_candidate_id(self):
        light.validate_response(self.response(),AUTHORS[0],self.pool)
        run=self.root/'run';(run/'work').mkdir(parents=True)
        (run/'work/full_domain_context.jsonl').write_text(json.dumps(dict(id='domain-P001',kind='problem'))+'\n')
        save(self.root/'ideas.json',[c['idea'] for c in self.pool[:5]])
        single.validate_cards(self.root/'ideas.json',run)
    def test_retain_cannot_mutate(self):
        r=copy.deepcopy(self.response());r['decisions'][0]['idea']['mechanism']='changed'
        with self.assertRaises(ValueError): light.validate_response(r,AUTHORS[0],self.pool)
    def test_cross_author_edit_rejected(self):
        r=self.response();r['decisions'][0]['card_id']='c-006'
        with self.assertRaises(ValueError): light.validate_response(r,AUTHORS[0],self.pool)
    def test_missing_author_blocks_generation(self):
        with self.assertRaises(ValueError): light.accepted_generation(self.root)
        self.assertFalse((self.root/'generation.json').exists())
    def test_missing_peer_blocks_discussion(self):
        rows=[dict(peer=a,card_ids=[next(c['card_id'] for c in self.pool if c['author']==a)],assessment='x',suggestion='y') for a in AUTHORS[1:]]
        light.validate_discussion(dict(author=AUTHORS[0],peer_notes=rows),AUTHORS[0],self.pool)
        with self.assertRaises(ValueError): light.validate_discussion(dict(author=AUTHORS[0],peer_notes=rows[:-1]),AUTHORS[0],self.pool)
    def test_withdrawn_or_invented_selection_rejected(self):
        pool=[dict(id=c['card_id'],**c['idea']) for c in self.pool[:5]]
        data=dict(top5=[dict(rank=i+1,card=c['id'],reason='value') for i,c in enumerate(pool)])
        light.validate_selection(data,pool)
        data['top5'][0]['card']='c-006'
        with self.assertRaises(ValueError): light.validate_selection(data,pool)
    def test_failed_author_never_advances(self):
        (self.root/'logs').mkdir()
        with patch.object(light.subprocess,'call',return_value=1),patch.object(light,'accepted_generation') as advance:
            with self.assertRaises(ValueError): light.domain_worker(self.root,'latent-reasoning')
        advance.assert_not_called()
        state=read(self.root/'domain_state.json')
        self.assertEqual(state['phase'],'generate');self.assertEqual(state['status'],'needs_review')
    def test_same_session_and_output_repair(self):
        run=self.root/'author';save(run/'work/library_api.json',{})
        save(run/'work/research_phase.json',{})
        (run/'work/out').mkdir(parents=True)
        output=run/'work/out/FINAL.json';calls=[]
        def fake_call(native,*args,**kw):
            calls.append((kw['thread_id'],kw['resume']))
            save(output,dict(valid=len(calls)==2))
            return dict(ok=True,session='original-session')
        def validator(data):
            if not data.get('valid'): raise ValueError('Incomplete output')
        with patch.object(light,'engine',return_value=single),patch.object(single.R,'recover_call',side_effect=fake_call),patch.object(single.isolate,'Gate'),patch.object(single,'audit'):
            light.invoke(run,'discuss','task',output,validator,'original-session')
        self.assertEqual(calls,[('original-session',True)]*2)
        self.assertTrue(read(run/'collaboration/discuss/accepted.json')['ok'])
    def test_changed_session_rejected(self):
        run=self.root/'author';output=run/'work/out/result.json'
        with patch.object(light,'engine',return_value=single),patch.object(single.R,'recover_call',return_value=dict(ok=True,session='other')),patch.object(single.isolate,'Gate'):
            with self.assertRaises(ValueError): light.invoke(run,'discuss','task',output,lambda _:None,'original')
    def test_context_complete_and_prompt_unchanged(self):
        domain='latent-reasoning';run=self.root/'single'
        single.prepare(run,domain)
        context=(SYSTEM/'domains'/domain/'full_context.jsonl').read_text()
        self.assertIn(context,(run/'initial_prompt.md').read_text())
        meta=read(run/'run.json');self.assertEqual(meta['prompt_template_sha256'],release_hash())
        self.assertEqual(read(run/'session.json')['status'],'prepared')
    def test_new_benchmark_export_preserves_full_idea(self):
        run=self.root/'run';(run/'work/out').mkdir(parents=True)
        save(run/'run.json',dict(domain_id='latent-reasoning'))
        save(run/'verification.json',dict(ok=True))
        cards=[idea(i) for i in range(5)];save(run/'work/out/IDEAS.json',cards)
        for n in ('IDEA.md','SEARCH_LOG.md'): (run/'work/out'/n).write_text('evidence')
        single.accept(run,cards)
        source=read(run/'evaluation_source.json')
        self.assertEqual(read(source['ideas']),cards)
        (run/'work/out/IDEAS.json').write_text('[]')
        from multi_source import validate_source
        with self.assertRaises(ValueError): validate_source(source)

    def test_blueprint_preparation_preserves_card_and_shared_full_context(self):
        import blueprint
        run=self.root/'single';single.prepare(run,'latent-reasoning')
        cards=[idea(i) for i in range(5)]
        save(run/'work/out/IDEAS.json',cards)
        for name in ('IDEA.md','SEARCH_LOG.md'):
            (run/'work/out'/name).write_text('Explicit source evidence from the offline fixture')
        save(run/'verification.json',dict(ok=True));single.accept(run,cards)
        source=read(run/'evaluation_source.json')
        save(run/'selector_top1.json',dict(original_rank=3,policy='Frozen offline selection',
            files={source['ideas']:source['ideas_sha256']}))
        out=self.root/'blueprint';manifest=blueprint.prepare_domain(run,out,'latent-reasoning')
        self.assertEqual(len(manifest['items']),5)
        self.assertEqual([i['rank'] for i in manifest['items'] if i['selector_top1']],[3])
        self.assertEqual(sha(out/'evidence/full_domain_context.jsonl'),
                         sha(SYSTEM/'domains/latent-reasoning/full_context.jsonl'))
        for i,item in enumerate(manifest['items']):
            self.assertEqual(read(out/'inputs'/item['id']/'original_idea.json'),cards[i])
        verify({out/k:v for k,v in manifest['files'].items()})

    def test_full_light_cycle_exact_top5_and_source_binding(self):
        root=self.root/'domain';domain='latent-reasoning';(root/'logs').mkdir(parents=True)
        def fake_author(command,**kwargs):
            author=command[command.index('--author')+1];phase=command[command.index('--phase')+1]
            run=root/'authors'/author;ai=AUTHORS.index(author)
            if phase=='generate':
                single.prepare(run,domain);cards=[idea(ai*5+i) for i in range(1,6)]
                save(run/'work/out/IDEAS.json',cards)
                for n in ('IDEA.md','SEARCH_LOG.md'): (run/'work/out'/n).write_text('genuine frozen generation placeholder for offline fixture')
                save(run/'verification.json',dict(ok=True));single.accept(run,cards)
                save(run/'session.json',dict(status='completed',session_id='session-'+author,stages={'1':dict(status='completed')}))
            elif phase=='discuss':
                pool=read(root/'generation.json')
                data=dict(author=author,peer_notes=[dict(peer=a,card_ids=[next(c['card_id'] for c in pool if c['author']==a)],assessment='mechanism assessment',suggestion='clarification') for a in AUTHORS if a!=author])
                light.validate_discussion(data,author,pool)
                output=run/'work/out/debate/DISCUSSION.json';save(output,data)
                save(run/'collaboration/discuss/accepted.json',dict(protected=read(run/'generation_seal.json')['files'],output_sha256=sha(output)))
            else:
                pool=read(root/'generation.json')
                data=dict(author=author,responses=[dict(critic=a,response='reasoned response') for a in AUTHORS if a!=author],
                    decisions=[dict(card_id=c['card_id'],action='retain',reason='mechanism retained',idea=c['idea']) for c in pool if c['author']==author])
                light.validate_response(data,author,pool)
                output=run/'work/out/debate/FINAL.json';save(output,data)
                save(run/'collaboration/respond/accepted.json',dict(protected=read(run/'generation_seal.json')['files'],output_sha256=sha(output)))
            return 0
        def fake_select(run,phase,prompt,output,validator):
            data=dict(top5=[dict(rank=i+1,card=f'c-{n:03d}',reason='independent value') for i,n in enumerate((2,8,13,23,30))])
            validator(data);save(output,data);return dict(session='independent-selector')
        with patch.object(light.subprocess,'call',side_effect=fake_author),patch.object(light,'engine',return_value=single),patch.object(light,'invoke',side_effect=fake_select):
            light.domain_worker(root,domain)
        self.assertEqual(read(root/'domain_state.json')['status'],'selected')
        final={c['id']:c for c in read(root/'final_pool.json')}
        selected=read(root/'selected/IDEAS.json')
        self.assertEqual(selected,[final[f'c-{n:03d}'] for n in (2,8,13,23,30)])
        from multi_source import validate_source
        validate_source(read(root/'evaluation_source.json'))
        self.assertEqual(read(root/'completion_check.json')['generation_cards'],30)

def release_hash(): return read(SYSTEM/'release.json')['template_sha256']

if __name__=='__main__': unittest.main()
