# In plain words

The same checklist picks the rulebooks (4 of 55). Then the search engine scores each individual rule (each numbered
paragraph) by how many words it shares with the product description, and the 190 best-matching rules are handed in.
It is the simplest baseline: fast and free. Its weakness is that word matching misses rules written in different words
and includes rules that only sound similar.

# Technical

1. Regulation selection: `regselect` `combined` (rules + supersession + vehicle-category filters): R48, R148, R150, R10.
2. Corpus: `data-ingestion/clauses` of the selected regulations, one chunk per clause (multi-page clauses cited at
   their first page), regulation title prefixed.
3. Queries: `spec_queries()` (about 25, from `spec.md`); retriever BM25+ (k1 1.2, b 0.75, delta 1) on unigrams +
   bigrams; per-query top 400 fused with reciprocal rank fusion (k0 60).
4. Output: top 190 clauses with paragraph (190 = dev gold size, declared in `risk.json`).
5. Dev: page P 0.32 / R 0.60 / F2 0.511, clause F2 0.148, regulation F2 1.0.
