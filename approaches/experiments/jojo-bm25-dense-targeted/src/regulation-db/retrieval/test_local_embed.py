"""Optional integration checks against the downloaded real local encoder."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np


@unittest.skipUnless(importlib.util.find_spec('fastembed') and
                     (Path(__file__).resolve().parent / 'model-cache').exists(),
                     'Requires optional FastEmbed and the local model download')
class LocalEncoderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from local_embed import CACHE, load
        cls.encoder, cls.tokenizer, cls.max_tokens, cls.identity = load(CACHE)

    def test_long_input_preserves_tail_and_stays_normalized(self):
        from local_embed import encode, segments
        text = 'Red rear position lamp. ' * 150 + 'Hydraulic brake stopping distance. ' * 150
        windows = segments(text, self.tokenizer, self.max_tokens)
        self.assertGreater(len(windows), 1)
        self.assertEqual(' '.join(' '.join(windows).split()), ' '.join(text.split()))
        self.assertTrue(all(len(self.tokenizer.encode(w).ids) <= self.max_tokens for w in windows))
        vectors, overflow = encode([text, windows[0]], self.encoder, self.tokenizer, self.max_tokens)
        self.assertEqual(overflow, 1)
        self.assertTrue(np.isfinite(vectors).all())
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6)
        self.assertFalse(np.allclose(vectors[0], vectors[1], atol=1e-4))


if __name__ == '__main__':
    unittest.main()
