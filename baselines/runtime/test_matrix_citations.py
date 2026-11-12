import unittest
from citations import extract


class MatrixCitationTests(unittest.TestCase):
    def test_middle_kernel_row_is_not_a_paper(self):
        ids,literals=extract({'method':'采用固定3×3核 [[1,2,1],[2,4,2],[1,2,1]]/16 模糊，参考[20134]。'})
        self.assertEqual(ids,[20134])
        self.assertEqual(len(literals),3)
        self.assertIn('[2,4,2]',[x['text'] for x in literals])

    def test_real_small_id_citations_still_require_evidence(self):
        ids,_=extract({'method':'参考 [2]、[4] 和 [2,4,2]；核 [[1,2],[3,4]]。'})
        self.assertEqual(ids,[2,4])

    def test_multiple_matrices_and_citations(self):
        ids,_=extract({'method':'A=[[1,2],[3,4],[5,6]]；B=[[7,8],[9,10]]；相关工作 [111743,20134]。'})
        self.assertEqual(ids,[20134,111743])

    def test_nonnumeric_brackets_are_not_matrix_evidence(self):
        ids,_=extract({'method':'[[1,2], text, [2,4,2], [1,2]] 与 [4]。'})
        self.assertEqual(ids,[2,4])

    def test_duplicate_middle_row_elsewhere_is_still_citation(self):
        ids,_=extract({'method':'[[1,2,1],[2,4,2],[1,2,1]]；另见文献 [2,4,2]。'})
        self.assertEqual(ids,[2,4])

    def test_chinese_adjacent_citation_and_ascii_index(self):
        ids,_=extract({'method':'参考[20134]，数组 x[2] 与 v[4]。'})
        self.assertEqual(ids,[20134])


if __name__=='__main__':unittest.main()
