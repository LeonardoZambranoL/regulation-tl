# In plain words

The same checklist picks the rulebooks. The shared database finds the rules whose meaning is closest to the product description, and each page of the rulebooks counts once, at its best rule. The 150 best pages are handed in, each with that rule's text and paragraph. Its weakness: it aims at the right pages, not at every right rule on them, and the size 150 was picked on the practice product.

# Technical

1. Regulation selection: `regselect` `combined`, as in devansh-bm25-pages-top150.
2. Retrieval: the team's shared vector database (`data-ingestion/.cache/lancedb`, table `clauses`: 26,769 clause vectors, `gemini-embedding-2-preview`, 768 dims); queries embedded with the same model via `data-ingestion/gemini_embedding.py`, exact cosine search restricted to the selected regulations (retriever `shared_db` in devansh-toolkit).
3. Queries: `spec_queries()`; per-query top 1000, RRF (k0 60); then one entry per (regulation, version, page): its best-ranked clause (`"dedupe": "page"`).
4. Output: top 150 pages, each cited with its best clause's paragraph (the BM25 page version had no paragraphs, so clause F2 0).
5. Scores: see the README "Results" section and the dashboard.
