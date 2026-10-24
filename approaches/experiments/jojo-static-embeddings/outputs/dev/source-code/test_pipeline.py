import unittest
import numpy as np
from catalog import batches, context_for, priority
from run import exact_decisions


class PipelineTests(unittest.TestCase):
    def test_no_clause_lost_at_batch_boundaries(self):
        rows = [{'id': str(i), 'text': 'x'*n} for i,n in enumerate([4,12,3,10,2])]
        result = list(batches(rows, size=2, max_chars=8))
        self.assertEqual([r for b in result for r in b], rows)

    def test_context_deduplicated_and_not_target(self):
        a = {'id':'a','ancestors':['b'],'references':['b','c']}
        b = {'id':'b','ancestors':[],'references':[]}
        c = {'id':'c','ancestors':[],'references':[]}
        self.assertEqual(context_for([a,b],{'a':a,'b':b,'c':c}),[c])

    def test_ranker_retains_every_record(self):
        rows = [{'id':str(i),'text':t} for i,t in enumerate(['lamp red light','brakes pedal','mirror visibility'])]
        score, audit = priority(rows, np.eye(3,dtype=np.float32), 'red lamp')
        self.assertEqual(len(score),len(rows))
        self.assertTrue(np.isfinite(score).all())
        self.assertEqual(audit['query_embedding_api_calls'],0)

    def test_incomplete_or_duplicated_decisions_rejected(self):
        d = {'id':'a','reason':'source evidence'}
        with self.assertRaises(ValueError):exact_decisions({'decisions':[d]}, {'a','b'})
        with self.assertRaises(ValueError):exact_decisions({'decisions':[d,d]}, {'a','b'})
        self.assertEqual(exact_decisions({'decisions':[d]}, {'a'}),[d])


if __name__ == '__main__':
    unittest.main()
