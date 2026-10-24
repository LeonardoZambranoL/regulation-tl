# In plain words

The same checklist as before picks the rulebooks (4 of 55 on the rear lamp). Then, instead of matching words, it uses the team's shared database of meaning fingerprints for every rule: each line of the product description gets a fingerprint too, and the rules whose meaning is closest are ranked first. The 190 best rules are handed in. Its weakness: "similar meaning" is not "applies", so related-but-wrong rules get in, and the size 190 was copied from the practice answer key.

# Technical

1. Regulation selection: `regselect` `combined` (rules + supersession + vehicle-category filters), as in devansh-bm25-clauses-top190.
2. Retrieval: the team's shared vector database (`data-ingestion/.cache/lancedb`, table `clauses`: 26,769 clause vectors, `gemini-embedding-2-preview`, 768 dims); queries embedded with the same model via `data-ingestion/gemini_embedding.py`, exact cosine search restricted to the selected regulations (retriever `shared_db` in devansh-toolkit).
3. Queries: `spec_queries()` (about 25, from `spec.md`, including the whole spec); per-query top 1000 fused with reciprocal rank fusion (k0 60).
4. Output: top 190 clauses with paragraph (190 = dev gold size, declared in `risk.json`).
5. Scores: see the README "Results" section and the dashboard.
