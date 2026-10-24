"""Hybrid BM25+ (with bigrams) + Precomputed Gemini-Embedding-2-Preview Retriever."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .llm import CachedLLMClient
from .stages.stage0_load import ClauseNode, LoadedCorpus

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[2]
EMB_PATH = REPO_ROOT / "data-ingestion" / "embeddings" / "gemini-embedding-2-preview_d768_n26769.npz"

TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


@dataclass
class RetrievalHit:
    clause: ClauseNode
    score: float
    bm25_score: float = 0.0
    dense_score: float = 0.0


class HybridRetriever:
    """Combines BM25+ (with bigrams) and precomputed 768-dim Gemini embeddings via RRF."""

    def __init__(
        self,
        corpus: LoadedCorpus,
        llm_client: CachedLLMClient | None = None,
        k1: float = 1.2,
        b: float = 0.75,
        delta: float = 1.0,
        bigrams: bool = True,
        rrf_k0: int = 60,
        use_dense: bool = True,
    ):
        self.corpus = corpus
        self.clauses = corpus.all_clauses
        self.llm_client = llm_client
        self.k1 = k1
        self.b = b
        self.delta = delta
        self.bigrams = bigrams
        self.rrf_k0 = rrf_k0
        self.use_dense = use_dense and EMB_PATH.is_file()

        self._build_bm25()
        self.emb_matrix: np.ndarray | None = None
        if self.use_dense:
            data = np.load(EMB_PATH, allow_pickle=False)
            vecs = data["embeddings"].astype(np.float32)
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self.emb_matrix = vecs / norms

    def _terms(self, text: str) -> list[str]:
        toks = tokenize(text)
        if self.bigrams and len(toks) > 1:
            return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        return toks

    def _build_bm25(self) -> None:
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        n = len(self.clauses)
        lengths = np.zeros(n, dtype=np.float32)
        for i, c in enumerate(self.clauses):
            reg_title = self.corpus.regulations[c.regulation].title
            doc_str = f"{c.regulation} {reg_title} {c.paragraph or ''} {c.text}"
            toks = self._terms(doc_str)
            lengths[i] = len(toks)
            for term, tf in Counter(toks).items():
                self.postings[term].append((i, tf))
        self.n = n
        mean_len = max(float(lengths.mean()), 1.0)
        self.norm = self.k1 * (1.0 - self.b + self.b * lengths / mean_len)
        self.idf = {
            t: math.log(1.0 + (self.n - len(ps) + 0.5) / (len(ps) + 0.5))
            for t, ps in self.postings.items()
        }

    def bm25_scores(self, query: str) -> np.ndarray:
        scores = np.zeros(self.n, dtype=np.float32)
        for term in sorted(set(self._terms(query))):
            ps = self.postings.get(term)
            if not ps:
                continue
            idx = np.fromiter((d for d, _ in ps), dtype=np.int64, count=len(ps))
            tf = np.fromiter((f for _, f in ps), dtype=np.float32, count=len(ps))
            scores[idx] += self.idf[term] * (tf * (self.k1 + 1.0) / (tf + self.norm[idx]) + self.delta)
        return scores

    def dense_scores(self, query: str) -> np.ndarray | None:
        if not self.use_dense or self.emb_matrix is None or self.llm_client is None:
            return None
        try:
            q_vec = self.llm_client.embed_query(query)
            return self.emb_matrix @ q_vec
        except Exception:
            return None

    def search(self, query: str, k: int = 30) -> list[RetrievalHit]:
        bm25_s = self.bm25_scores(query)
        dense_s = self.dense_scores(query)

        top_pool = min(max(k * 5, 150), self.n)
        bm25_top = np.argpartition(-bm25_s, top_pool - 1)[:top_pool]
        bm25_top = bm25_top[np.lexsort((bm25_top, -bm25_s[bm25_top]))]

        if dense_s is None:
            chosen = bm25_top[:k]
            return [
                RetrievalHit(
                    clause=self.clauses[int(i)],
                    score=float(bm25_s[int(i)]),
                    bm25_score=float(bm25_s[int(i)]),
                    dense_score=0.0,
                )
                for i in chosen
                if bm25_s[int(i)] > 0
            ]

        dense_top = np.argpartition(-dense_s, top_pool - 1)[:top_pool]
        dense_top = dense_top[np.lexsort((dense_top, -dense_s[dense_top]))]

        rrf_scores: dict[int, float] = defaultdict(float)
        for rank, idx in enumerate(bm25_top, 1):
            if bm25_s[int(idx)] > 0:
                rrf_scores[int(idx)] += 1.0 / (self.rrf_k0 + rank)
        for rank, idx in enumerate(dense_top, 1):
            rrf_scores[int(idx)] += 1.0 / (self.rrf_k0 + rank)

        ranked = sorted(rrf_scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        return [
            RetrievalHit(
                clause=self.clauses[i],
                score=float(rrf_s),
                bm25_score=float(bm25_s[i]),
                dense_score=float(dense_s[i]),
            )
            for i, rrf_s in ranked
        ]
