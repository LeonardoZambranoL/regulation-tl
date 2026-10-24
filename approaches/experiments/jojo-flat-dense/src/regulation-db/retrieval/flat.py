"""Exact cosine search: score every vector, with no lexical or ANN index."""
from pathlib import Path
import time

import numpy as np
from hybrid import digest, read_json, read_lines, unit_vectors


class FlatRetriever:
    def __init__(self, index, block_size=8192):
        if not isinstance(block_size, int) or block_size < 1:
            raise ValueError('block_size must be a positive integer.')
        self.block_size = block_size
        index = Path(index)
        self.manifest = read_json(index / 'manifest.json')
        self.chunks = read_lines(index / 'chunks.jsonl')
        fingerprint = digest('\n'.join(c['id'] + ':' + digest(c['search_text']) for c in self.chunks))
        self.dense_meta = read_json(index / 'dense.json')
        self.dense = np.load(index / 'dense.npy', mmap_mode='r', allow_pickle=False)
        if (not self.chunks or fingerprint != self.manifest['fingerprint'] or
                fingerprint != self.dense_meta['fingerprint'] or
                self.dense.shape != (len(self.chunks), self.dense_meta['dimensions']) or
                not np.isfinite(self.dense).all()):
            raise ValueError('Dense index does not match corpus.')
        norms = np.linalg.norm(self.dense.astype(np.float64), axis=1)
        if not np.allclose(norms, 1, atol=1e-5):
            raise ValueError('Flat cosine search requires normalized document vectors.')
        self.last_scan = None

    def retrieve(self, query, vector, model, limit=20, regulations=None):
        if not isinstance(limit, int) or limit < 1:
            raise ValueError('limit must be a positive integer.')
        if model != self.dense_meta['model']:
            raise ValueError('Query and corpus embedding model identifiers must match.')
        q = unit_vectors([vector])[0]
        if q.shape != (self.dense.shape[1],):
            raise ValueError('Query embedding dimension mismatch.')
        start = time.perf_counter()
        scores = np.empty(len(self.chunks), dtype=np.float32)
        for first in range(0, len(scores), self.block_size):
            end = min(first + self.block_size, len(scores))
            scores[first:end] = self.dense[first:end] @ q
        # Scope is applied AFTER scanning every vector. None and empty set differ.
        ids = np.array([i for i, c in enumerate(self.chunks)
                        if regulations is None or c['regulation'] in regulations], dtype=int)
        ordered = ids[np.argsort(-scores[ids], kind='stable')]
        seen, results = set(), []
        # Deduplicate before taking top-k clauses; duplicate windows cannot exhaust a pool.
        for i in ordered:
            chunk = self.chunks[int(i)]
            if chunk['clause_id'] in seen:
                continue
            seen.add(chunk['clause_id'])
            results.append({**chunk, 'score': float(scores[i]), 'cosine': float(scores[i])})
            if len(results) == limit:
                break
        self.last_scan = {'vectors_scanned': len(scores), 'eligible_vectors': len(ids),
                          'returned_clauses': len(results), 'dimensions': self.dense.shape[1],
                          'seconds': time.perf_counter() - start,
                          'scope_filter': 'after full scan', 'exact': True}
        return results
