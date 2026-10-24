# devansh-llm-clause-filter-writer

Owner: Devansh. **Current best for the platform's requirement-level score.** Same clause selection as
[devansh-llm-clause-filter](../devansh-llm-clause-filter/), plus a writer step that turns each kept clause into the
single obligations it states. Code: [devansh-toolkit](../devansh-toolkit/) (`retrieval/write.py`, `retrieval/export.py`).

## Why

The uploaded devansh-llm-clause-filter file (308 raw clauses) scored requirements P 33.4% / R 54.2% / F2 48.2% on the
platform, although its pages (R 98%) and regulations (100%) were right. The platform matches requirements one to one
with the experts' list, whose entries are single obligations (190 from 121 paragraphs; one R10 paragraph alone gives 10).
A whole clause can match at most one of them, and headings, numbers and non-obligations cost precision.

## Method

See [EXPLAIN.md](EXPLAIN.md) "Technical". Config: `config.json` (`"write": {"prompt": "strict"}`).

## How to run

```bash
# ANTHROPIC_API_KEY in the git-ignored .env (your own key); answers are cached in devansh-toolkit/.cache
cd approaches/experiments/devansh-toolkit/src
python -m retrieval.export --config ../../devansh-llm-clause-filter-writer/config.json --team-id team-11 --out ../../devansh-llm-clause-filter-writer/outputs/predictions.json
python -m retrieval.export --config ../../devansh-llm-clause-filter-writer/config.json --case holdout-acpe --team-id team-11 --out ../../devansh-llm-clause-filter-writer/outputs/predictions-holdout-acpe.json
cd ../../../..
python approaches/benchmarking/bench.py devansh-llm-clause-filter-writer approaches/experiments/devansh-llm-clause-filter-writer/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
python approaches/benchmarking/req_judge.py approaches/experiments/devansh-llm-clause-filter-writer/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json
```

For the held-out case: `--case <held-out case id>` (put its `spec.md` under `approaches/benchmarking/cases/<id>/` or in
the challenge repo's `cases/`), then `python ../industrial-ai-hackathon/tools/validate.py <file>` before uploading.

## Results (2026-10-24)

Requirement level from the local judge (`approaches/benchmarking/req_judge.py`; on the uploaded raw-clause file it gave
P 0.338 / R 0.547 / F2 0.487 vs the platform's 0.334 / 0.542 / 0.482, i.e. 104 vs 103 matches).

| variant (dev rear lamp) | requirements | req P | req R | **req F2** |
|---|---|---|---|---|
| raw clauses (devansh-llm-clause-filter, uploaded) | 308 | 0.338 | 0.547 | 0.487 |
| writer, default prompt | 523 | 0.296 | 0.816 | 0.604 |
| **writer, strict prompt (this experiment)** | **328** | **0.448** | **0.774** | **0.676** |
| strict writer on em_devansh-dynregex-neutral clauses | 334 | 0.434 | 0.763 | 0.663 |
| strict writer on em_devansh-llm-clause-filter clauses | 361 | 0.418 | 0.795 | 0.674 |

Unseen ACPE case (its answer key is the sub-goal's whole-R175 list, administrative duties included, so it understates
precision and penalises the strict prompt): req F2 0.390 (raw clauses 0.383; neutral base 0.335). Page level dev:
P 0.680 / R 0.962 / F2 0.888; regulation 1.0.

Where the remaining error is (dev, this experiment): 137 of the 181 unmatched requirements come from paragraphs
the experts did not list, so precision is decided by clause selection; 32 of the 43 missed expert requirements come
from paragraphs we never kept.

## Assumptions and limitations

- Overfit risk medium (`risk.json`): regulation rules and the writer's style rules were written while looking at the
  dev case; nothing numeric was fitted. Prompts are generic (no product terms).
- LLM output varies run to run; it is cached per batch, so a rerun reproduces the same file.
