import unittest
from citations import extract


class ProgramArrayTests(unittest.TestCase):
    def test_function_example_and_real_citation(self):
        report={'example':'zup([1,2,3])=[2,3,1]，dax([1,2,3])=[1,2]，zup dax([4,5,6])=[5,6]。应输出 [8,9,7]。依据[9668]。'}
        ids,literals=extract(report)
        self.assertEqual(ids,[9668])
        self.assertEqual(len(literals),7)

    def test_small_citation_outside_example_still_required(self):
        ids,literals=extract({'example':'f([1,2])=[2,1]；这些方法见[1,2]。'})
        self.assertEqual(ids,[1,2])
        self.assertEqual(len(literals),2)

    def test_only_explicit_function_syntax(self):
        ids,literals=extract({'text':'例如[1,2]，f([3,4] 描述不完整。'})
        self.assertEqual(ids,[1,2,3,4])
        self.assertFalse(literals)

    def test_single_id_not_excluded_by_output_words(self):
        ids,literals=extract({'text':'应输出 [42]；参见[2,4]。'})
        self.assertEqual(ids,[2,4,42])
        self.assertFalse(literals)

    def test_unrelated_equation_still_validates_citations(self):
        ids,literals=extract({'text':'score=[1,2]，see result [3,4]。'})
        self.assertEqual(ids,[1,2,3,4])
        self.assertFalse(literals)
