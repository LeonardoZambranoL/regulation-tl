"""Retrievers made of other retrievers: fusion (hybrid search) and reranking (multi-stage funnels).

    {"type": "rrf", "retrievers": [{"type": "bm25"}, {"type": "dense", "model": "BAAI/bge-small-en-v1.5"}]}
    {"type": "rerank", "first_stage": {...any config...}, "model": "BAAI/bge-reranker-base", "candidates": 200}
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from ..corpus import Chunk
from .base import Hit, Retriever, build, chunk_text, register


@register("rrf")
class RRF(Retriever):
    """Reciprocal Rank Fusion (Cormack et al. 2009): score = sum_i w_i / (k0 + rank_i). Needs no score calibration,
    which is why it is the default way to combine BM25 with dense retrieval.
    params: retrievers=[configs], weights=[1,...], k0=60, depth=200 (how deep each retriever is read)
    """

    def fit(self, chunks: list[Chunk]):
        self.subs = [build(c).fit(chunks) for c in self.params["retrievers"]]
        self.weights = self.params.get("weights") or [1.0] * len(self.subs)
        return self

    def search_many(self, queries: list[str], k: int = 100) -> list[list[Hit]]:
        depth, k0 = max(k, self.params.get("depth", 200)), self.params.get("k0", 60)
        per_sub = [s.search_many(queries, depth) for s in self.subs]
        out = []
        for qi in range(len(queries)):
            fused: dict[int, float] = defaultdict(float)
            for w, results in zip(self.weights, per_sub):
                for rank, h in enumerate(results[qi]):
                    fused[h.chunk_id] += w / (k0 + rank + 1)
            out.append([Hit(c, s) for c, s in sorted(fused.items(), key=lambda x: -x[1])[:k]])
        return out

    def search(self, query: str, k: int = 100) -> list[Hit]:
        return self.search_many([query], k)[0]


@register("score_fusion")
class ScoreFusion(RRF):
    """Convex combination of min-max normalised scores (a.k.a. 'alpha' hybrid). Sometimes beats RRF when one
    retriever is clearly stronger; tune the weights on the dev case.
    params: retrievers, weights, depth=200
    """

    def search_many(self, queries: list[str], k: int = 100) -> list[list[Hit]]:
        depth = max(k, self.params.get("depth", 200))
        per_sub = [s.search_many(queries, depth) for s in self.subs]
        out = []
        for qi in range(len(queries)):
            fused: dict[int, float] = defaultdict(float)
            for w, results in zip(self.weights, per_sub):
                hits = results[qi]
                if not hits:
                    continue
                hi, lo = hits[0].score, hits[-1].score
                for h in hits:
                    fused[h.chunk_id] += w * ((h.score - lo) / (hi - lo) if hi > lo else 1.0)
            out.append([Hit(c, s) for c, s in sorted(fused.items(), key=lambda x: -x[1])[:k]])
        return out


@register("rerank")
class CrossEncoderRerank(Retriever):
    """Two-stage funnel: a cheap first stage proposes `candidates`, a cross-encoder reads (query, chunk) pairs jointly
    and reorders them. Raises precision at the top; recall is capped by the first stage, so keep candidates high.
    Models: BAAI/bge-reranker-base, BAAI/bge-reranker-v2-m3, cross-encoder/ms-marco-MiniLM-L-6-v2,
            mixedbread-ai/mxbai-rerank-base-v1, Alibaba-NLP/gte-reranker-modernbert-base
    params: first_stage={config}, model, candidates=100, batch_size=32, keep_tail=True
    """

    def fit(self, chunks: list[Chunk]):
        from sentence_transformers import CrossEncoder
        self.first = build(self.params["first_stage"]).fit(chunks)
        self.text = {c.id: chunk_text(c) for c in chunks}
        self.model = CrossEncoder(self.params.get("model", "BAAI/bge-reranker-base"), max_length=512)
        return self

    def search_many(self, queries: list[str], k: int = 100) -> list[list[Hit]]:
        n = max(k, self.params.get("candidates", 100))
        out = []
        for q, hits in zip(queries, self.first.search_many(queries, n)):
            if not hits:
                out.append([])
                continue
            scores = self.model.predict([(q, self.text[h.chunk_id]) for h in hits],
                                        batch_size=self.params.get("batch_size", 32), show_progress_bar=False)
            order = np.argsort(-np.asarray(scores))
            out.append([Hit(hits[i].chunk_id, float(scores[i])) for i in order][:k])
        return out

    def search(self, query: str, k: int = 100) -> list[Hit]:
        return self.search_many([query], k)[0]
