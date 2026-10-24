import unittest
from unittest.mock import Mock
import numpy as np
from splade_pipeline import SparseDense, rerank, sparse_encode


class Tokenizer:
    def encode(self, text):
        return Mock(ids=text.split())


class SparseTests(unittest.TestCase):
    def engine(self):
        e = SparseDense.__new__(SparseDense)
        e.base = Mock()
        e.base.chunks = [{'id': str(i), 'clause_id': str(i)} for i in range(3)]
        e.base.scores.return_value = (np.array([0,1,2]),np.zeros(3),np.array([0.8,0.9,0.1]))
        e.offsets = np.array([0,2,3])
        e.docs = np.array([0,2,1])
        e.values = np.array([2.,1.,3.])
        return e

    def test_union_retains_single_channel_candidates_and_deduplicates(self):
        e = self.engine()
        rows, union = e.retrieve('q',[1.],'model',pool=1,limit=10,sparse_vector={0:1.})
        self.assertEqual({r['id'] for r in union},{'0','1'})
        self.assertEqual(len(rows),2)
        self.assertAlmostEqual(rows[0]['score'],1/61)

    def test_filters_apply_to_both_modalities(self):
        e = self.engine()
        e.base.scores.return_value = (np.array([1,2]),np.zeros(2),np.array([.9,.1]))
        rows, _ = e.retrieve('q',[1.],'model',pool=2,limit=10,sparse_vector={0:1.},regulations=['allowed'])
        self.assertNotIn('0',{r['id'] for r in rows})

    def test_zero_sparse_does_not_invent_matches(self):
        rows, _ = self.engine().retrieve('q',[1.],'model',method='splade',sparse_vector={})
        self.assertEqual(rows,[])

    def test_nonfinite_weight_rejected(self):
        with self.assertRaises(ValueError):
            self.engine().retrieve('q',[1.],'model',sparse_vector={0:float('nan')})

    def test_max_pooling_preserves_overflow_terms(self):
        model = Mock()
        model.embed.return_value = iter([Mock(indices=[1],values=[2.]),Mock(indices=[1,2],values=[1.,3.])])
        result = sparse_encode(['a b c d'],(model,Tokenizer(),2,'x'))
        self.assertEqual(result,[{1:2.,2:3.}])

    def test_rerank_only_reorders_head_preserves_tail_and_evidence(self):
        model = Mock()
        model.rerank.return_value = [-1.,2.]
        rows = [{'id':str(i),'search_text':'source','page_start':i+1} for i in range(4)]
        result = rerank('query',rows,(model,Tokenizer(),512,'x'),2)
        self.assertEqual([r['id'] for r in result],['1','0','2','3'])
        self.assertEqual(result[0]['page_start'],2)
        self.assertEqual(result[2:],rows[2:])


if __name__ == '__main__':
    unittest.main()
