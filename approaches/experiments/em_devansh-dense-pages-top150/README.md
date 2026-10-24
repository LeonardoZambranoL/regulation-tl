# em_devansh-dense-pages-top150

Owner: Devansh. Embedded (`em_`) version of [devansh-bm25-pages-top150](../devansh-bm25-pages-top150/): BM25+ over PDF pages replaced by Gemini embeddings over clauses, aggregated per page; pages now carry a paragraph.
Code: [devansh-toolkit](../devansh-toolkit/) (`retrieval/retrievers/shared_db.py`, `retrieval/export.py`).

## Method

1. Regulation selection: `regselect` `combined`, as in devansh-bm25-pages-top150.
2. Retrieval: the team's shared vector database (`data-ingestion/.cache/lancedb`, table `clauses`: 26,769 clause vectors, `gemini-embedding-2-preview`, 768 dims); queries embedded with the same model via `data-ingestion/gemini_embedding.py`, exact cosine search restricted to the selected regulations (retriever `shared_db` in devansh-toolkit).
3. Queries: `spec_queries()`; per-query top 1000, RRF (k0 60); then one entry per (regulation, version, page): its best-ranked clause (`"dedupe": "page"`).
4. Output: top 150 pages, each cited with its best clause's paragraph (the BM25 page version had no paragraphs, so clause F2 0).

## How to run

```bash
# once, from the repo root: shared vector database (no API key needed)
python -m pip install -r data-ingestion/requirements-vectors.txt
python data-ingestion/import_vectors.py
# GEMINI_API_KEY (query embeddings) in the git-ignored .env: your own keys
cd approaches/experiments/devansh-toolkit/src
python -m retrieval.export --config ../../em_devansh-dense-pages-top150/config.json --out ../../em_devansh-dense-pages-top150/outputs/predictions.json
python -m retrieval.export --config ../../em_devansh-dense-pages-top150/config.json --case holdout-acpe --out ../../em_devansh-dense-pages-top150/outputs/predictions-holdout-acpe.json
cd ../../../..
python approaches/benchmarking/bench.py em_devansh-dense-pages-top150 approaches/experiments/em_devansh-dense-pages-top150/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
python approaches/benchmarking/bench.py em_devansh-dense-pages-top150 approaches/experiments/em_devansh-dense-pages-top150/outputs/predictions-holdout-acpe.json approaches/benchmarking/cases/holdout-acpe/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

## Assumptions and limitations

- Needs the shared database built locally (git-ignored) and a Gemini key for query embeddings; query vectors are cached
  in `devansh-toolkit/.cache/gemini_queries`, so reruns make no Gemini calls.
- Overfit risk: see `risk.json` (inherits the base experiment's dev-informed choices; nothing new tuned on dev).

## Results

First run, 2026-10-24, compared with the base version (devansh-bm25-pages-top150):

| case | version | page P | page R | page F2 | clause R | clause F2 | regulation F2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev (rear lamp) | base | 0.280 | 0.792 | 0.580 | 0.000 | 0.000 | 1.000 |
| dev (rear lamp) | **em_** | 0.233 | 0.660 | 0.483 | 0.041 | 0.039 | 1.000 |
| unseen (ACPE) | base | not run | | | | | |
| unseen (ACPE) | **em_** | 0.060 | 1.000 | 0.242 | 0.035 | 0.029 | 0.833 |

Risk declared: medium (see `risk.json`).
