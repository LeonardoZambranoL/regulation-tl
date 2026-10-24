# devansh-toolkit: Devansh's shared code (not a ranked experiment)

Owner: Devansh. The code behind every `devansh-*` experiment: regulation selection, a plug-and-play retrieval lab, the
LLM clause classifier, and export to the submission format. It has no predictions of its own; the ranked experiments
are the folders below, each with its own `config.json`, `risk.json`, README and results.

| experiment | what it does | page F2 | clause F2 |
|---|---|---|---|
| [devansh-llm-clause-filter](../devansh-llm-clause-filter/) | rules pick the regulations, Claude keeps or drops each "shall" clause | **0.844** | **0.619** |
| [devansh-bm25-pages-top150](../devansh-bm25-pages-top150/) | rules pick the regulations, BM25+ ranks whole pages, top 150 (no LLM) | 0.580 | 0.000 |
| [devansh-bm25-clauses-top190](../devansh-bm25-clauses-top190/) | rules pick the regulations, BM25+ ranks clauses, top 190 (no LLM) | 0.511 | 0.148 |

Pipeline: spec -> **select applicable regulations** (`regselect`) -> candidates from the team's `data-ingestion/clauses`
-> rank (BM25+, TF-IDF, dense, hybrids...) or classify (`classify`, Claude) -> cite page + paragraph (`export`).
Everything tried so far, with scores and lessons: [HISTORY.md](HISTORY.md).

## Layout

```text
README.md            this file
requirements.txt     pymupdf, numpy, jsonschema (+ src/retrieval/requirements-neural.txt for dense/SPLADE/rerank, anthropic for LLM)
setup.sh / setup.ps1 venv + deps + clones the challenge repo next to this repo
src/retrieval/       the lab: corpus, retrievers, regselect, bench, oracle, export (full docs in its README)
HISTORY.md           every experiment so far, with scores
```

## Run

```bash
cd approaches/experiments/devansh-toolkit
./setup.sh                 # Windows: .\setup.ps1   (add --neural / -Neural for dense, SPLADE, rerank)
cd src
../.venv/bin/python -m retrieval.regselect                 # every selection method vs gold (Windows: ..\.venv\Scripts\python)
../.venv/bin/python -m retrieval.bench --list              # all retriever configs
../.venv/bin/python -m retrieval.bench retrieval/configs/sel_rules_bm25plus_bigrams.json
../.venv/bin/python -m retrieval.oracle                    # what perfect selection / filtering would be worth
../.venv/bin/python -m retrieval.export --config ../../devansh-llm-clause-filter/config.json --out ../../devansh-llm-clause-filter/outputs/predictions.json
cd ../../../..             # repo root, then score on the team leaderboard:
python approaches/benchmarking/bench.py devansh-llm-clause-filter approaches/experiments/devansh-llm-clause-filter/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

LLM steps (`regselect --method llm`, `select: {"method": "llm"}` in a config) read `ANTHROPIC_API_KEY` from the
environment or from a git-ignored `.env` (repo root or this folder). Never commit it. LLM answers are cached in `.cache/`.

## Versions and reproducibility

- Python 3.13; numpy 2.4, pymupdf 1.28; anthropic 2.3 (LLM selector); model `claude-opus-5-5`, effort high.
- Lexical retrieval and the rules selector are deterministic (no seeds involved). The LLM selector is not; its answer
  for each (spec, prompt) is cached so benchmark runs are repeatable.
- Data: `data-ingestion/clauses` (team parse of the base PDFs) as of commit 6a1b5e9.

## Findings so far

| step | page F1 (our bench, N=190) | reg F1 |
|---|---|---|
| retrieval only, best lexical (rrf bm25+ bigrams + char tf-idf) | 0.28 | 0.33 |
| + rules regulation selection (bm25+ bigrams, clauses) | **0.42** | **1.00** |
| + LLM regulation selection (same retriever) | 0.42 | 1.00 (same 4 regulations, independently) |
| scope-BM25 selection (no rules, no LLM) | 0.38 | 0.50 |
| oracle: perfect regs + every "shall" clause | 0.34 (P 0.20, R 1.00) | 1.00 |

With the right regulations, every gold requirement is among about 1,200 "shall" clauses, so the remaining work is
picking the right about 190 of them (LLM clause classifier) and rewriting them as single obligations.

## Comparison dashboard

All experiments are compared on https://claude.ai/artifact/TEW2x5Fhkj8DHgtmfnLLTV. How to add yours, declare its
overfitting risk and refresh the dashboard: [approaches/dashboard/README.md](../../dashboard/README.md).
