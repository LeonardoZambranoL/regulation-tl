"""A pipeline = a chunking granularity + a retriever config. This is what the rest of the project should call.

    from retrieval.pipeline import Pipeline
    pipe = Pipeline.from_file("retrieval/configs/bm25.json")
    for chunk, score in pipe.search("stop lamp luminous intensity", k=20):
        print(chunk.cite(), chunk.text[:80])
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .corpus import Chunk, load_corpus
from .retrievers import build


class Pipeline:
    def __init__(self, config: dict):
        self.config = config
        self.name = config.get("name", config["retriever"]["type"])
        self.source = config.get("source", "clauses")
        self.chunks: list[Chunk] = load_corpus(config.get("granularity", "paragraph"), self.source)
        self.by_id = {c.id: c for c in self.chunks}
        self.retriever = build(config["retriever"]).fit(self.chunks)

    @classmethod
    def from_file(cls, path: str | Path) -> "Pipeline":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def search(self, query: str, k: int = 50) -> list[tuple[Chunk, float]]:
        return self.search_many([query], k)[0]

    def search_many(self, queries: list[str], k: int = 50) -> list[list[tuple[Chunk, float]]]:
        return [[(self.by_id[h.chunk_id], h.score) for h in hits] for hits in self.retriever.search_many(queries, k)]

    def pooled(self, queries: list[str], k_per_query: int = 100, k0: int = 60) -> list[tuple[Chunk, float]]:
        """Run many queries (e.g. one per product function / part) and fuse them with RRF into one candidate list."""
        fused: dict[int, float] = defaultdict(float)
        for results in self.search_many(queries, k_per_query):
            for rank, (c, _) in enumerate(results):
                fused[c.id] += 1.0 / (k0 + rank + 1)
        return [(self.by_id[i], s) for i, s in sorted(fused.items(), key=lambda x: -x[1])]


def spec_queries(spec_md: str) -> list[str]:
    """Turn a product spec (markdown) into search queries: the product itself, each function, each part, each material row,
    and part x product combinations, so that every aspect of the product gets its own shot at the corpus."""
    product = ""
    queries, section = [], ""
    for line in spec_md.splitlines():
        s = line.strip()
        if s.startswith("#"):
            section = s.lstrip("# ").lower()
            continue
        if not s or set(s) <= set("|- "):
            continue
        if section.startswith("product type") and not product:
            product = re.split(r"\s+[—-]\s+", s)[0].strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if cells and cells[0].lower() not in ("component",):
                queries.append(" ".join(cells))
        else:
            queries.append(s.lstrip("-* ").strip())
    parts = [q for q in queries if len(q.split()) <= 4]
    queries += [f"{product} {p}" for p in parts if product and product.lower() not in p.lower()]
    queries.append(spec_md)  # the whole spec as one long query
    return [q for q in dict.fromkeys(queries) if q]
