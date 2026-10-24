# em_devansh-dynregex-llm-clause-filter

Owner: Devansh. Embedded (`em_`) version of [devansh-dynregex-llm-clause-filter](../devansh-dynregex-llm-clause-filter/): Candidate list widened by the shared Gemini database (300 non-shall clauses); everything else unchanged.
Code: [devansh-toolkit](../devansh-toolkit/) (`retrieval/retrievers/shared_db.py`, `retrieval/export.py`).

## Method

1. Regulation selection: `regselect` `llm_regex` (cached per spec).
2. Candidates: every `\b(shall|must)\b` clause of the selected regulations (unchanged order, cached decisions reused), plus the 300 best non-shall clauses from the team's shared vector database (`data-ingestion/.cache/lancedb`, table `clauses`: 26,769 clause vectors, `gemini-embedding-2-preview`, 768 dims); queries embedded with the same model via `data-ingestion/gemini_embedding.py`, exact cosine search restricted to the selected regulations (retriever `shared_db` in devansh-toolkit); queries `spec_queries()`, RRF (k0 60).
3. Classifier: single agent, `claude-opus-5-5` effort medium, structured output, batches of 40, cached per batch.
4. Output: every kept clause as one requirement; no size cut.

## How to run

```bash
# once, from the repo root: shared vector database (no API key needed)
python -m pip install -r data-ingestion/requirements-vectors.txt
python data-ingestion/import_vectors.py
# GEMINI_API_KEY (query embeddings) and ANTHROPIC_API_KEY (classifier) in the git-ignored .env: your own keys
cd approaches/experiments/devansh-toolkit/src
python -m retrieval.export --config ../../em_devansh-dynregex-llm-clause-filter/config.json --out ../../em_devansh-dynregex-llm-clause-filter/outputs/predictions.json
python -m retrieval.export --config ../../em_devansh-dynregex-llm-clause-filter/config.json --case holdout-acpe --out ../../em_devansh-dynregex-llm-clause-filter/outputs/predictions-holdout-acpe.json
cd ../../../..
python approaches/benchmarking/bench.py em_devansh-dynregex-llm-clause-filter approaches/experiments/em_devansh-dynregex-llm-clause-filter/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
python approaches/benchmarking/bench.py em_devansh-dynregex-llm-clause-filter approaches/experiments/em_devansh-dynregex-llm-clause-filter/outputs/predictions-holdout-acpe.json approaches/benchmarking/cases/holdout-acpe/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

## Assumptions and limitations

- Needs the shared database built locally (git-ignored) and a Gemini key for query embeddings; query vectors are cached
  in `devansh-toolkit/.cache/gemini_queries`, so reruns make no Gemini calls.
- Overfit risk: see `risk.json` (inherits the base experiment's dev-informed choices; nothing new tuned on dev).

## Results

First run, 2026-10-24, compared with the base version (devansh-dynregex-llm-clause-filter):

| case | version | page P | page R | page F2 | clause R | clause F2 | regulation F2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev (rear lamp) | base | 0.409 | 0.981 | 0.767 | 0.810 | 0.561 | 0.909 |
| dev (rear lamp) | **em_** | 0.390 | 1.000 | 0.761 | 0.860 | 0.546 | 0.909 |
| unseen (ACPE) | base | 0.096 | 0.875 | 0.333 | 0.842 | 0.476 | 0.500 |
| unseen (ACPE) | **em_** | 0.080 | 0.875 | 0.292 | 0.842 | 0.433 | 0.500 |

Risk declared: medium (see `risk.json`).
