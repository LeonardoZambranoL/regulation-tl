# devansh-dynregex-allclauses-neutral

Owner: Devansh. **Claude writes regex patterns from the spec to pick the regulations, then one Claude agent with a
product-neutral prompt judges every clause (no "shall" filter).** Designed to generalise: no hand-written product
rules, no product examples in the prompt, no size cut. Scored on dev-rear-lamp **and** on the unseen holdout-acpe case.

## Why

On the dev case 23 of 121 gold clauses never reached the reviewers because they do not contain "shall" / "must"
(spec-style lines, "is not permitted", test instructions), capping clause recall at 0.81 for every LLM variant. This
variant removes that filter and tells the reviewer that obligations can be implicit.

## How it works

See [EXPLAIN.md](EXPLAIN.md) (plain words and technical steps). Config: `config.json`.
Code: `../devansh-toolkit/src/retrieval` (`regselect.py` `llm_regex`, `classify.py` `NEUTRAL_INSTRUCTIONS` and
`candidates(..., "all")`, `export.py`).

## Run

```bash
cd approaches/experiments/devansh-toolkit/src      # after ../setup.sh; needs ANTHROPIC_API_KEY or a git-ignored .env
../.venv/bin/python -m retrieval.export --config ../../devansh-dynregex-allclauses-neutral/config.json --out ../../devansh-dynregex-allclauses-neutral/outputs/predictions.json
../.venv/bin/python -m retrieval.export --config ../../devansh-dynregex-allclauses-neutral/config.json --case holdout-acpe --out ../../devansh-dynregex-allclauses-neutral/outputs/predictions-holdout-acpe.json
cd ../../../..
python approaches/benchmarking/bench.py devansh-dynregex-allclauses-neutral approaches/experiments/devansh-dynregex-allclauses-neutral/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
python approaches/benchmarking/bench.py devansh-dynregex-allclauses-neutral approaches/experiments/devansh-dynregex-allclauses-neutral/outputs/predictions-holdout-acpe.json approaches/benchmarking/cases/holdout-acpe/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

Cost: about 290 reviewer calls for both cases on a first run; cached afterwards.

## Assumptions and limitations

- The prompt's examples of implicit wording were chosen after looking at dev misses (declared in `risk.json`).
- Regex selection can pick regulations that match by accident (e.g. R83 for ACPE); the reviewer must reject their rules.
- Requirement text is the raw clause, not yet split into single obligations.
