"""Neural retrievers. Optional: they need `pip install -r retrieval/requirements-neural.txt`.

Embeddings are cached in .cache/ per (model, corpus), so a second run of the benchmark is fast.
"""

from __future__ import annotations

import hashlib

import numpy as np

from ..corpus import CACHE_DIR, Chunk
from .base import Hit, Retriever, chunk_text, register
from .lexical import _top_k


def _cache_key(*parts) -> str:
    return hashlib.sha1(repr(parts).encode()).hexdigest()[:12]


@register("dense")
class Dense(Retriever):
    """Bi-encoder (sentence-transformers) + exact cosine search. Exact search = recall 1.0 w.r.t. the embedding, the
    reference that ANN indexes (hnsw) are measured against. ~37k chunks fits in RAM easily.

    Good models to try (all on Hugging Face):
      BAAI/bge-small-en-v1.5 (fast)  BAAI/bge-base-en-v1.5  BAAI/bge-m3 (8k ctx)  intfloat/e5-base-v2
      nomic-ai/nomic-embed-text-v1.5  Alibaba-NLP/gte-modernbert-base  Qwen/Qwen3-Embedding-0.6B
    params: model, query_prefix="", doc_prefix="", batch_size=64, max_seq_length=512, device=None
    """

    def _model(self):
        if not hasattr(self, "_m"):
            from sentence_transformers import SentenceTransformer
            p = self.params
            self._m = SentenceTransformer(p.get("model", "BAAI/bge-small-en-v1.5"), device=p.get("device"),
                                          trust_remote_code=p.get("trust_remote_code", False))
            self._m.max_seq_length = p.get("max_seq_length", 512)
        return self._m

    def _encode(self, texts: list[str], prefix: str) -> np.ndarray:
        return self._model().encode([prefix + t for t in texts], batch_size=self.params.get("batch_size", 64),
                                    normalize_embeddings=True, show_progress_bar=len(texts) > 1000,
                                    convert_to_numpy=True).astype(np.float32)

    def fit(self, chunks: list[Chunk]):
        texts = [chunk_text(c) for c in chunks]
        key = _cache_key(self.params.get("model"), self.params.get("doc_prefix", ""), len(texts), texts[0], texts[-1])
        path = CACHE_DIR / f"emb_{key}.npy"
        if path.is_file():
            self.emb = np.load(path)
        else:
            self.emb = self._encode(texts, self.params.get("doc_prefix", ""))
            CACHE_DIR.mkdir(exist_ok=True)
            np.save(path, self.emb)
        self.ids = [c.id for c in chunks]
        return self

    def search(self, query: str, k: int = 100) -> list[Hit]:
        return self.search_many([query], k)[0]

    def search_many(self, queries: list[str], k: int = 100) -> list[list[Hit]]:
        q = self._encode(queries, self.params.get("query_prefix", ""))
        return [_top_k(row, k, self.ids) for row in q @ self.emb.T]


@register("hnsw")
class HNSW(Dense):
    """Dense embeddings + HNSW graph index (Malkov & Yashunin) via faiss. Tune ef_search up for recall -> 1.0.
    Only worth it over `dense` at millions of chunks; here it shows how close ANN gets to exact.
    params: everything Dense takes, plus M=32, ef_construction=200, ef_search=256
    """

    def fit(self, chunks: list[Chunk]):
        import faiss
        super().fit(chunks)
        self.index = faiss.IndexHNSWFlat(self.emb.shape[1], self.params.get("M", 32), faiss.METRIC_INNER_PRODUCT)
        self.index.hnsw.efConstruction = self.params.get("ef_construction", 200)
        self.index.add(self.emb)
        self.index.hnsw.efSearch = self.params.get("ef_search", 256)
        return self

    def search_many(self, queries: list[str], k: int = 100) -> list[list[Hit]]:
        q = self._encode(queries, self.params.get("query_prefix", ""))
        scores, idx = self.index.search(q, k)
        return [[Hit(self.ids[i], float(s)) for s, i in zip(srow, irow) if i >= 0] for srow, irow in zip(scores, idx)]


@register("splade")
class Splade(Retriever):
    """Learned sparse retrieval (SPLADE, Formal et al.; high-recall use: Yang, SIGIR 2024). The model expands each text
    into weighted vocabulary terms, so it matches synonyms like dense models but keeps exact-term precision like BM25.
    params: model="naver/splade-cocondenser-ensembledistil", batch_size=16, max_length=256
    """

    def _load(self):
        if not hasattr(self, "_tok"):
            import torch
            from transformers import AutoModelForMaskedLM, AutoTokenizer
            name = self.params.get("model", "naver/splade-cocondenser-ensembledistil")
            self._torch = torch
            self._tok = AutoTokenizer.from_pretrained(name)
            self._mlm = AutoModelForMaskedLM.from_pretrained(name).eval()

    def _encode(self, texts: list[str]):
        import scipy.sparse as sp
        self._load()
        torch, rows = self._torch, []
        bs = self.params.get("batch_size", 16)
        for i in range(0, len(texts), bs):
            enc = self._tok(texts[i:i + bs], padding=True, truncation=True, return_tensors="pt",
                            max_length=self.params.get("max_length", 256))
            with torch.no_grad():
                logits = self._mlm(**enc).logits
            w = torch.max(torch.log1p(torch.relu(logits)) * enc["attention_mask"].unsqueeze(-1), dim=1).values
            rows.append(sp.csr_matrix(w.numpy()))
        return sp.vstack(rows).tocsr()

    def fit(self, chunks: list[Chunk]):
        import scipy.sparse as sp
        texts = [chunk_text(c) for c in chunks]
        key = _cache_key(self.params.get("model"), len(texts), texts[0], texts[-1])
        path = CACHE_DIR / f"splade_{key}.npz"
        if path.is_file():
            self.mat = sp.load_npz(path)
        else:
            self.mat = self._encode(texts)
            CACHE_DIR.mkdir(exist_ok=True)
            sp.save_npz(path, self.mat)
        self.mat_t = self.mat.T.tocsr()
        self.ids = [c.id for c in chunks]
        return self

    def search_many(self, queries: list[str], k: int = 100) -> list[list[Hit]]:
        scores = (self._encode(queries) @ self.mat_t).toarray()
        return [_top_k(row, k, self.ids) for row in scores]

    def search(self, query: str, k: int = 100) -> list[Hit]:
        return self.search_many([query], k)[0]
