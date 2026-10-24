# em_devansh-dense-clauses-top190

Owner: Devansh. Embedded (`em_`) version of [devansh-bm25-clauses-top190](../devansh-bm25-clauses-top190/): BM25+ (words) replaced by Gemini embeddings (meaning); everything else identical.
Code: [devansh-toolkit](../devansh-toolkit/) (`retrieval/retrievers/shared_db.py`, `retrieval/export.py`).

## Method

1. Regulation selection: `regselect` `combined` (rules + supersession + vehicle-category filters), as in devansh-bm25-clauses-top190.
2. Retrieval: the team's shared vector database (`data-ingestion/.cache/lancedb`, table `clauses`: 26,769 clause vectors, `gemini-embedding-2-preview`, 768 dims); queries embedded with the same model via `data-ingestion/gemini_embedding.py`, exact cosine search restricted to the selected regulations (retriever `shared_db` in devansh-toolkit).
3. Queries: `spec_queries()` (about 25, from `spec.md`, including the whole spec); per-query top 1000 fused with reciprocal rank fusion (k0 60).
4. Output: top 190 clauses with paragraph (190 = dev gold size, declared in `risk.json`).

## How to run

```bash
# once, from the repo root: shared vector database (no API key needed)
python -m pip install -r data-ingestion/requirements-vectors.txt
python data-ingestion/import_vectors.py
# GEMINI_API_KEY (query embeddings) in the git-ignored .env: your own keys
cd approaches/experiments/devansh-toolkit/src
python -m retrieval.export --config ../../em_devansh-dense-clauses-top190/config.json --out ../../em_devansh-dense-clauses-top190/outputs/predictions.json
python -m retrieval.export --config ../../em_devansh-dense-clauses-top190/config.json --case holdout-acpe --out ../../em_devansh-dense-clauses-top190/outputs/predictions-holdout-acpe.json
cd ../../../..
python approaches/benchmarking/bench.py em_devansh-dense-clauses-top190 approaches/experiments/em_devansh-dense-clauses-top190/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
python approaches/benchmarking/bench.py em_devansh-dense-clauses-top190 approaches/experiments/em_devansh-dense-clauses-top190/outputs/predictions-holdout-acpe.json approaches/benchmarking/cases/holdout-acpe/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

## Assumptions and limitations

- Needs the shared database built locally (git-ignored) and a Gemini key for query embeddings; query vectors are cached
  in `devansh-toolkit/.cache/gemini_queries`, so reruns make no Gemini calls.
- Overfit risk: see `risk.json` (inherits the base experiment's dev-informed choices; nothing new tuned on dev).

## Results

First run, 2026-10-24, compared with the base version (devansh-bm25-clauses-top190):

| case | version | page P | page R | page F2 | clause R | clause F2 | regulation F2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev (rear lamp) | base | 0.317 | 0.604 | 0.511 | 0.165 | 0.148 | 1.000 |
| dev (rear lamp) | **em_** | 0.258 | 0.472 | 0.405 | 0.066 | 0.059 | 0.789 |
| unseen (ACPE) | base | 0.160 | 1.000 | 0.488 | 0.789 | 0.549 | 0.833 |
| unseen (ACPE) | **em_** | 0.113 | 1.000 | 0.388 | 0.632 | 0.436 | 0.833 |

Risk declared: medium (see `risk.json`).
