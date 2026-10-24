import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from flat import FlatRetriever
from hybrid import digest, unit_vectors


class FlatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = Path(self.tmp.name)
        self.chunks = [{'id': str(i), 'clause_id': c, 'search_text': str(i),
                        'regulation': r} for i, (c, r) in enumerate(
                            [('a','R1'), ('a','R1'), ('b','R2'), ('c','R1'), ('d','R1')])]
        fp = digest('\n'.join(c['id'] + ':' + digest(c['search_text']) for c in self.chunks))
        (p/'chunks.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in self.chunks))
        (p/'manifest.json').write_text(json.dumps({'fingerprint':fp}))
        (p/'dense.json').write_text(json.dumps({'fingerprint':fp,'dimensions':2,'model':'test'}))
        self.vectors = unit_vectors([[1,0],[1,0],[0.9,0.1],[0,1],[0,1]])
        np.save(p/'dense.npy',self.vectors)
        self.engine = FlatRetriever(p, block_size=2)

    def test_exhaustive_oracle_and_duplicate_windows(self):
        hits = self.engine.retrieve('x',[1,0],'test',limit=4)
        self.assertEqual([r['id'] for r in hits], ['0','2','3','4'])
        oracle = self.vectors @ np.array([1,0],dtype=np.float32)
        np.testing.assert_allclose([r['score'] for r in hits],oracle[[0,2,3,4]])
        self.assertEqual(self.engine.last_scan['vectors_scanned'],5)

    def test_filter_still_scans_every_vector(self):
        hits = self.engine.retrieve('x',[1,0],'test',limit=3,regulations={'R2'})
        self.assertEqual([r['id'] for r in hits],['2'])
        self.assertEqual(self.engine.last_scan['vectors_scanned'],5)
        self.assertEqual(self.engine.retrieve('x',[1,0],'test',regulations=set()),[])

    def test_embedding_contract(self):
        for vector,model in [([1,0],'wrong'),([1,0,0],'test'),([0,0],'test'),([np.nan,1],'test')]:
            with self.assertRaises(ValueError):
                self.engine.retrieve('x',vector,model)


if __name__ == '__main__':
    unittest.main()
