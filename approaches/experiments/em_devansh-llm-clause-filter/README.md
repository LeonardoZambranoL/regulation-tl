# em_devansh-llm-clause-filter

Owner: Devansh. Embedded (`em_`) version of [devansh-llm-clause-filter](../devansh-llm-clause-filter/): Candidate list widened by the shared Gemini database (300 non-shall clauses); classifier and prompt unchanged.
Code: [devansh-toolkit](../devansh-toolkit/) (`retrieval/retrievers/shared_db.py`, `retrieval/export.py`).

## Method

1. Regulation selection: `regselect` `combined`.
2. Candidates: every `\b(shall|must)\b` clause of the selected regulations (unchanged, same order, so cached decisions are reused), plus the 300 best non-shall clauses of the same regulations from the team's shared vector database (`data-ingestion/.cache/lancedb`, table `clauses`: 26,769 clause vectors, `gemini-embedding-2-preview`, 768 dims); queries embedded with the same model via `data-ingestion/gemini_embedding.py`, exact cosine search restricted to the selected regulations (retriever `shared_db` in devansh-toolkit); queries `spec_queries()`, RRF (k0 60).
3. Classifier: `claude-opus-5-5`, effort medium, structured output, batches of 40, the devansh-llm-clause-filter prompt, cached per batch.
4. Output: every kept clause as one requirement; no size cut.

## How to run

```bash
# once, from the repo root: shared vector database (no API key needed)
python -m pip install -r data-ingestion/requirements-vectors.txt
python data-ingestion/import_vectors.py
# GEMINI_API_KEY (query embeddings) and ANTHROPIC_API_KEY (classifier) in the git-ignored .env: your own keys
cd approaches/experiments/devansh-toolkit/src
python -m retrieval.export --config ../../em_devansh-llm-clause-filter/config.json --out ../../em_devansh-llm-clause-filter/outputs/predictions.json
python -m retrieval.export --config ../../em_devansh-llm-clause-filter/config.json --case holdout-acpe --out ../../em_devansh-llm-clause-filter/outputs/predictions-holdout-acpe.json
cd ../../../..
python approaches/benchmarking/bench.py em_devansh-llm-clause-filter approaches/experiments/em_devansh-llm-clause-filter/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
python approaches/benchmarking/bench.py em_devansh-llm-clause-filter approaches/experiments/em_devansh-llm-clause-filter/outputs/predictions-holdout-acpe.json approaches/benchmarking/cases/holdout-acpe/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

## Assumptions and limitations

- Needs the shared database built locally (git-ignored) and a Gemini key for query embeddings; query vectors are cached
  in `devansh-toolkit/.cache/gemini_queries`, so reruns make no Gemini calls.
- Overfit risk: see `risk.json` (inherits the base experiment's dev-informed choices; nothing new tuned on dev).

## Results

First run, 2026-10-24, compared with the base version (devansh-llm-clause-filter):

| case | version | page P | page R | page F2 | clause R | clause F2 | regulation F2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev (rear lamp) | base | 0.542 | 0.981 | 0.844 | 0.810 | 0.619 | 1.000 |
| dev (rear lamp) | **em_** | 0.491 | 1.000 | 0.828 | 0.843 | 0.585 | 1.000 |
| unseen (ACPE) | base | 0.167 | 1.000 | 0.500 | 0.737 | 0.512 | 0.833 |
| unseen (ACPE) | **em_** | 0.143 | 1.000 | 0.455 | 0.754 | 0.434 | 0.833 |

Risk declared: medium (see `risk.json`).
