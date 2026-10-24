"""Dense search over the team's shared vector database (data-ingestion/.cache/lancedb, table "clauses").

The clause vectors are the team's Gemini embeddings (gemini-embedding-2-preview, 768 dims, cosine); queries are
embedded with the same model through data-ingestion/gemini_embedding.py. Build the database once (no API key):

    python -m pip install -r data-ingestion/requirements-vectors.txt
    python data-ingestion/import_vectors.py

Queries need GEMINI_API_KEY (environment or the git-ignored .env). Query vectors are cached in .cache/, so a rerun makes
no Gemini calls. Only works on source "clauses" (the database holds clauses, not PDF pages).
    params: k_db=1000 (hits fetched per query before the regulation filter), model, dimensions
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np

from ..corpus import CACHE_DIR, REPO_ROOT, Chunk
from .base import Hit, Retriever, register

DB_DIR = REPO_ROOT / "data-ingestion" / ".cache" / "lancedb"
MODEL = "gemini-embedding-2-preview"
DIMENSIONS = 768


def embed_query(text: str, model: str = MODEL, dimensions: int = DIMENSIONS) -> np.ndarray:
    """Normalised query vector, cached per (model, dimensions, text)."""
    key = hashlib.sha1(f"{model}|{dimensions}|{text}".encode()).hexdigest()[:16]
    cache = CACHE_DIR / "gemini_queries" / f"{key}.npy"
    if cache.is_file():
        return np.load(cache)
    from ..llm import load_env
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set: add it to the git-ignored .env at the repo root (your own key)")
    sys.path.insert(0, str(REPO_ROOT / "data-ingestion"))
    from gemini_embedding import embed_text
    vector = embed_text(text, model=model, dimensions=dimensions, api_key=api_key)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, vector)
    return vector


@register("shared_db")
class SharedDB(Retriever):
    """Exact cosine search in the shared LanceDB table, restricted to the chunks this pipeline was fitted on."""

    def fit(self, chunks: list[Chunk]) -> "SharedDB":
        import lancedb

        if not DB_DIR.is_dir():
            raise SystemExit(f"shared vector database not found at {DB_DIR}: run python data-ingestion/import_vectors.py")
        manifest = DB_DIR / "manifest.json"
        if manifest.is_file():
            model = json.loads(manifest.read_text(encoding="utf-8")).get("model", MODEL)
            if self.params.get("model", MODEL) != model:
                raise SystemExit(f"query model {self.params.get('model', MODEL)} != database model {model}")
        self.by_clause = {c.meta["clause_id"]: c.id for c in chunks if c.meta and "clause_id" in c.meta}
        if not self.by_clause:
            raise SystemExit("shared_db needs source 'clauses' (chunks carry the database clause_id)")
        self.regulations = sorted({c.regulation for c in chunks})
        self.table = lancedb.connect(str(DB_DIR)).open_table("clauses")
        return self

    def search(self, query: str, k: int = 100) -> list[Hit]:
        vector = embed_query(query, self.params.get("model", MODEL), self.params.get("dimensions", DIMENSIONS))
        regs = ", ".join("'" + r.replace("'", "''") + "'" for r in self.regulations)
        rows = (self.table.search(vector).distance_type("cosine").where(f"regulation IN ({regs})", prefilter=True)
                .select(["clause_id", "_distance"]).limit(max(k, self.params.get("k_db", 1000))).to_list())
        hits = [Hit(self.by_clause[r["clause_id"]], 1.0 - float(r["_distance"])) for r in rows if r["clause_id"] in self.by_clause]
        return hits[:k]
