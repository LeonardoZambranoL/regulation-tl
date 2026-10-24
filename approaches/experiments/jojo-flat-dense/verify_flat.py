"""Compare real-corpus Flat top-100 rankings with independent per-vector dot products."""
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'src/regulation-db/retrieval'))
from flat import FlatRetriever
from local_embed import load, encode, CACHE
from hybrid import DEFAULT_INDEX, unit_vectors


def main():
    start = time.perf_counter()
    retriever = FlatRetriever(DEFAULT_INDEX)
    loaded = time.perf_counter() - start
    encoder, tokenizer, maximum, identity = load(CACHE)
    queries = ['rear position lamp red light',
               'electromagnetic compatibility electronic lamp controller',
               'stop lamp installation visibility angles']
    vectors, _ = encode(queries, encoder, tokenizer, maximum, query=True)
    tests = []
    positions = {c['id']: i for i, c in enumerate(retriever.chunks)}
    for query, vector in zip(queries, vectors):
        hits = retriever.retrieve(query, vector, identity, limit=100)
        q = unit_vectors([vector])[0]
        scores = np.array([np.dot(row, q) for row in retriever.dense])
        ordered = np.argsort(-scores, kind='stable')
        seen, oracle = set(), []
        for i in ordered:
            clause = retriever.chunks[int(i)]
            if clause['clause_id'] not in seen:
                seen.add(clause['clause_id'])
                oracle.append(clause['id'])
            if len(oracle) == 100:
                break
        if [h['id'] for h in hits] != oracle:
            raise AssertionError('Top-100 clause ranking differs from independent oracle.')
        np.testing.assert_allclose([h['score'] for h in hits],
                                   [scores[positions[h['id']]] for h in hits], atol=1e-6)
        tests.append({'query': query, 'oracle_top100_equal': True, **retriever.last_scan})
    report = {'python': platform.python_version(), 'numpy': np.__version__,
              'index_load_seconds': loaded, 'embedding': retriever.dense_meta,
              'index_fingerprint': retriever.manifest['fingerprint'],
              'matrix_bytes': retriever.dense.nbytes, 'tests': tests, 'gold_access': False,
              'note': 'Independent per-vector dot-product oracle; timings include scan/sort/dedup, exclude encoding and index load.'}
    (ROOT / 'retrieval-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
