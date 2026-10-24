"""Generate, verify, and save shareable Gemini Embedding vectors for all clauses in `data-ingestion/clauses`.

Usage:
    .venv/bin/python data-ingestion/embed_clauses.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from retrieval.corpus import load_corpus
from retrieval.retrievers.neural import Gemini


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--model",
        default="gemini-embedding-2-preview",
        help="Embedding model name (default: gemini-embedding-2-preview)",
    )
    ap.add_argument("--dim", type=int, default=768, help="Matryoshka output dimensionality (default: 768)")
    ap.add_argument("--batch-size", type=int, default=50, help="Clauses per batch step (default: 50)")
    ap.add_argument("--workers", type=int, default=16, help="Concurrent threads for single-item API (default: 16)")
    args = ap.parse_args()

    chunks = load_corpus(granularity="paragraph", source="clauses")
    print(f"Loaded {len(chunks)} clauses from data-ingestion/clauses/")

    retriever = Gemini(
        model=args.model,
        output_dimensionality=args.dim,
        batch_size=args.batch_size,
        max_workers=args.workers,
        delay=0.0,
    )
    retriever.fit(chunks)
    shared_path = retriever._shared_path(len(chunks)).relative_to(REPO_ROOT)

    emb = retriever.emb
    unique_rows = len(np.unique(emb, axis=0))
    norms = np.linalg.norm(emb, axis=1)
    print("\n=== Verification ===")
    print(f"  File:        {shared_path} ({(REPO_ROOT / shared_path).stat().st_size / (1024 * 1024):.1f} MB)")
    print(f"  Shape:       {emb.shape}")
    print(f"  Unique rows: {unique_rows}/{len(emb)} ({unique_rows * 100 / len(emb):.1f}%)")
    print(f"  L2 norms:    min={norms.min():.4f}, max={norms.max():.4f}")

    test_query = "stop lamp luminous intensity requirements"
    hits = retriever.search(test_query, k=3)
    print(f"\n  Sanity search: {test_query!r}")
    for rank, h in enumerate(hits, 1):
        c = chunks[h.chunk_id]
        snippet = " ".join(c.text.split())[:100]
        print(f"    {rank}. [{h.score:.4f}] {c.regulation} p.{c.page} ({c.paragraph}): {snippet}...")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
