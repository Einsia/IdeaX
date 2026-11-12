import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import rescore as R


class ContractTests(unittest.TestCase):
    def test_missing_and_invalid_scores_are_not_zero(self):
        for invalid in [None, True, -1, 0, 11, 2.5, float('nan')]:
            with self.assertRaises(ValueError):
                R.validate('relevance', {'relevance': {'score': invalid, 'reasoning': 'reason'}}, {})

    def test_chinese_transfer_quote_and_fabricated_quote(self):
        raw={k:'supported' for k in ('source_setting','target_setting','transferred_mechanism','shared_structure','adaptation')}
        raw.update(score=1,reasoning='结构支持',evidence_quote='从控制理论借用稳定性分析')
        req={'mechanism':'我们从控制理论借用稳定性分析，用于约束逐步推理误差。'}
        self.assertEqual(R.validate('transfer',raw,req)['score'],1)
        raw['evidence_quote']='这段引文在提案中没有出现'
        self.assertEqual(R.validate('transfer',raw,req)['score'],0)

    def test_reference_projection_does_not_reveal_results(self):
        packet={'reference_materials':[{'kind':'paper','doc_id':'paper:1','read_depth':'source_card',
             'content':{'title':'t','abstract':'MEASURED_OUTCOME','observations':['MEASURED_OUTCOME'],
                        'evaluation':{'result':'MEASURED_OUTCOME'},'problem':{'statement':'p'},
                        'insight':{'mechanism':'m'}}}]}
        rendered,n=R.reference_block(packet)
        self.assertEqual(n,1)
        self.assertNotIn('MEASURED_OUTCOME',rendered)
        with self.assertRaises(ValueError):R.reference_block({'reference_materials':[]})

    def test_mechanism_excludes_experiment_and_related_work(self):
        idea=json.dumps({'title':'t','problem':'p','mechanism':'mechanism'*2000,
                         'previous_work':'forbidden','experiment':'forbidden'})
        block=R.mechanism_block(idea)
        self.assertNotIn('forbidden',block)
        self.assertGreater(len(block),5000)

    def test_relevance_uses_assigned_task_not_answer(self):
        packet={'idea_text':json.dumps({'title':'t','problem':'AUTHOR_CHOSEN_PROBLEM','mechanism':'m'}),
                'reference_materials':[{'kind':'paper','doc_id':'paper:1','read_depth':'source_card','content':{'title':'t'}}]}
        req=R.requests(packet,{'prompt':'ASSIGNED_TASK','scope_boundary':'BOUNDARY'})
        prefix=req['relevance']['user'].split('# PROPOSED SOLUTION')[0]
        self.assertIn('ASSIGNED_TASK',prefix)
        self.assertNotIn('AUTHOR_CHOSEN_PROBLEM',prefix)


if __name__=='__main__':unittest.main()
