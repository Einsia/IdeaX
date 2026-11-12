import json
from pathlib import Path
import tempfile
import unittest
from citations import extract
from isci_delivery import canonical
from outcomes import record_rejection,aggregate,REJECTION


class RecoveryTests(unittest.TestCase):
    def test_code_matrix_and_ranges_are_not_citations(self):
        report=dict(code='for j in [1, 2, 3]:\n    pass',matrix='C=[[1,1],[1,1]]；参考 [2266102][2294565]',
            evaluation='整数区间为 [1,100] 或 [20,80]；依据 [47710]，截到 [1,100]。')
        ids,ignored=extract(report)
        self.assertEqual(ids,[47710,2266102,2294565]);self.assertEqual(len(ignored),6)

    def test_unknown_scholarly_citations_still_require_validation(self):
        ids,_=extract({'research':'已有工作 [1,2,3] 与 [9999999]；实验组 tensor[12]。'})
        self.assertEqual(ids,[1,2,3,9999999])

    def test_missing_substantive_fields_are_not_filled(self):
        with self.assertRaises(ValueError):canonical({'proposal':{'title':'Only title'}})

    def test_only_terminal_novelty_rejection_creates_zero_slot(self):
        with tempfile.TemporaryDirectory(dir=__import__('os').environ.get('IDEAX_SCRATCH')) as tmp:
            run=Path(tmp);native=run/'native/run-01';native.mkdir(parents=True);log=native/'attempt-1.log'
            log.write_text('TimeoutError: provider timed out\n')
            with self.assertRaises(ValueError):record_rejection(native,'domain',1,log)
            log.write_text('native novelty trials\n'+REJECTION+'\n')
            outcome=record_rejection(native,'domain',1,log)
            self.assertEqual(outcome['score'],0);self.assertFalse((native/'idea_card.json').exists())
            rows=aggregate(run);self.assertEqual(len(rows),1);self.assertTrue(rows[0]['include_in_denominator'])
            log.write_text('modified evidence')
            with self.assertRaises(ValueError):aggregate(run)


if __name__=='__main__':unittest.main()
