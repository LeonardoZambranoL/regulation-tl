"""Lexical retrievers: no model, no GPU, just numpy. Strong baselines for regulation text, which is full of exact terms
("stop lamp", "retro-reflector", "IP code") that dense models can blur."""

from __future__ import annotations

import math
from collections import Counter, defaultdict

import numpy as np

from ..corpus import Chunk
from .base import Hit, Retriever, chunk_text, register, tokenize


@register("bm25")
class BM25(Retriever):
    """Okapi BM25 (Robertson & Jones). variant="plus" gives BM25+ (Lv & Zhai 2011), which stops long paragraphs
    from being under-scored - useful because regulation paragraphs vary from one line to a full page.

    params: k1=1.2, b=0.75, variant="okapi"|"plus", delta=1.0, with_title=True, bigrams=False
    """

    def fit(self, chunks: list[Chunk]):
        p = self.params
        self.k1, self.b = p.get("k1", 1.2), p.get("b", 0.75)
        self.delta = p.get("delta", 1.0) if p.get("variant", "okapi") == "plus" else 0.0
        self.bigrams = p.get("bigrams", False)
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        lengths = np.zeros(len(chunks), dtype=np.float32)
        for i, c in enumerate(chunks):
            toks = self._terms(chunk_text(c, p.get("with_title", True)))
            lengths[i] = len(toks)
            for term, tf in Counter(toks).items():
                self.postings[term].append((i, tf))
        self.n = len(chunks)
        self.norm = self.k1 * (1 - self.b + self.b * lengths / max(lengths.mean(), 1.0))
        self.idf = {t: math.log(1 + (self.n - len(ps) + 0.5) / (len(ps) + 0.5)) for t, ps in self.postings.items()}
        self.ids = [c.id for c in chunks]
        return self

    def _terms(self, text: str) -> list[str]:
        toks = tokenize(text)
        return toks + [a + "_" + b for a, b in zip(toks, toks[1:])] if self.bigrams else toks

    def scores(self, query: str) -> np.ndarray:
        s = np.zeros(self.n, dtype=np.float32)
        for term in set(self._terms(query)):
            ps = self.postings.get(term)
            if not ps:
                continue
            idx = np.fromiter((d for d, _ in ps), dtype=np.int64, count=len(ps))
            tf = np.fromiter((f for _, f in ps), dtype=np.float32, count=len(ps))
            s[idx] += self.idf[term] * (tf * (self.k1 + 1) / (tf + self.norm[idx]) + self.delta)
        return s

    def search(self, query: str, k: int = 100) -> list[Hit]:
        return _top_k(self.scores(query), k, self.ids)


@register("tfidf")
class TfIdf(Retriever):
    """Cosine similarity over sublinear TF-IDF vectors. analyzer="char" uses character 3-5 grams, which tolerates
    hyphenation and spelling variants from PDF extraction (retro-reflector / retroreflector).

    params: analyzer="word"|"char", ngram=(3,5), with_title=True
    """

    def _features(self, text: str) -> Counter:
        if self.params.get("analyzer", "word") == "char":
            lo, hi = self.params.get("ngram", (3, 5))
            t = " " + " ".join(tokenize(text)) + " "
            return Counter(t[i:i + n] for n in range(lo, hi + 1) for i in range(len(t) - n + 1))
        return Counter(tokenize(text))

    def fit(self, chunks: list[Chunk]):
        feats = [self._features(chunk_text(c, self.params.get("with_title", True))) for c in chunks]
        df = Counter(t for f in feats for t in f)
        self.n = len(chunks)
        self.idf = {t: math.log((1 + self.n) / (1 + d)) + 1 for t, d in df.items()}
        self.postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for i, f in enumerate(feats):
            w = {t: (1 + math.log(tf)) * self.idf[t] for t, tf in f.items()}
            norm = math.sqrt(sum(v * v for v in w.values())) or 1.0
            for t, v in w.items():
                self.postings[t].append((i, v / norm))
        self.ids = [c.id for c in chunks]
        return self

    def search(self, query: str, k: int = 100) -> list[Hit]:
        q = {t: (1 + math.log(tf)) * self.idf[t] for t, tf in self._features(query).items() if t in self.idf}
        qn = math.sqrt(sum(v * v for v in q.values())) or 1.0
        s = np.zeros(self.n, dtype=np.float32)
        for t, qv in q.items():
            ps = self.postings[t]
            idx = np.fromiter((d for d, _ in ps), dtype=np.int64, count=len(ps))
            val = np.fromiter((v for _, v in ps), dtype=np.float32, count=len(ps))
            s[idx] += qv / qn * val
        return _top_k(s, k, self.ids)


def _top_k(scores: np.ndarray, k: int, ids: list[int]) -> list[Hit]:
    k = min(k, len(scores))
    top = np.argpartition(-scores, k - 1)[:k]
    top = top[np.argsort(-scores[top])]
    return [Hit(ids[i], float(scores[i])) for i in top if scores[i] > 0]
