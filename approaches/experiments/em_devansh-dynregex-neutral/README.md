# em_devansh-dynregex-neutral

Owner: Devansh. Embedded (`em_`) version of [devansh-dynregex-allclauses-neutral](../devansh-dynregex-allclauses-neutral/): instead of judging every clause, Claude judges the shall clauses plus the shared Gemini database's 300 closest non-shall clauses; selection and neutral prompt unchanged.
Code: [devansh-toolkit](../devansh-toolkit/) (`retrieval/retrievers/shared_db.py`, `retrieval/export.py`).

## Method

1. Regulation selection: `regselect` `llm_regex` (cached per spec).
2. Candidates (`shall+db`): every `\b(shall|must)\b` clause of the selected regulations, plus the 300 best non-shall clauses of the same regulations from the team's shared vector database (`data-ingestion/.cache/lancedb`, `gemini-embedding-2-preview`, 768 dims, exact cosine; retriever `shared_db`), queries `spec_queries()`, RRF (k0 60).
3. Classifier: single agent, `claude-opus-5-5` effort medium, structured output, batches of 40, the `neutral` prompt, cached per batch.
4. Output: every kept clause as one requirement; no size cut.

## How to run

```bash
# once, from the repo root: shared vector database (no API key needed)
python -m pip install -r data-ingestion/requirements-vectors.txt
python data-ingestion/import_vectors.py
# GEMINI_API_KEY (query embeddings) and ANTHROPIC_API_KEY (classifier) in the git-ignored .env: your own keys
cd approaches/experiments/devansh-toolkit/src
python -m retrieval.export --config ../../em_devansh-dynregex-neutral/config.json --out ../../em_devansh-dynregex-neutral/outputs/predictions.json
python -m retrieval.export --config ../../em_devansh-dynregex-neutral/config.json --case holdout-acpe --out ../../em_devansh-dynregex-neutral/outputs/predictions-holdout-acpe.json
cd ../../../..
python approaches/benchmarking/bench.py em_devansh-dynregex-neutral approaches/experiments/em_devansh-dynregex-neutral/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
python approaches/benchmarking/bench.py em_devansh-dynregex-neutral approaches/experiments/em_devansh-dynregex-neutral/outputs/predictions-holdout-acpe.json approaches/benchmarking/cases/holdout-acpe/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

## Assumptions and limitations

- Needs the shared database built locally (git-ignored) and a Gemini key for query embeddings; query vectors are cached
  in `devansh-toolkit/.cache/gemini_queries`, so reruns make no Gemini calls.
- Overfit risk: see `risk.json` (inherits the base experiment's dev-informed choices; nothing new tuned on dev).

## Results

First run, 2026-10-24, compared with the base version (devansh-dynregex-allclauses-neutral):

| case | version | page P | page R | page F2 | clause R | clause F2 | regulation F2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev (rear lamp) | base | 0.312 | 1.000 | 0.694 | 0.917 | 0.496 | 0.909 |
| dev (rear lamp) | **em_** | 0.465 | 1.000 | 0.813 | 0.818 | 0.582 | 0.952 |
| unseen (ACPE) | base | 0.089 | 1.000 | 0.328 | 0.860 | 0.377 | 0.500 |
| unseen (ACPE) | **em_** | 0.095 | 1.000 | 0.345 | 0.789 | 0.412 | 0.500 |

Risk declared: medium (see `risk.json`).
