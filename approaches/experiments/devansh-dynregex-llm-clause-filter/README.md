# devansh-dynregex-llm-clause-filter

Owner: Devansh. **Claude writes regex patterns from the spec to pick the regulations, then one Claude agent keeps or drops each "shall" clause.** Compare with devansh-llm-clause-filter (hand-written rules, one agent).

## What it does and how it works

Nothing is hand-written for the product. Claude reads only the product description (not the list of rulebooks, not the answers) and writes search patterns for its functions and parts, like "stop lamp" or "retro-reflect". Those patterns are searched in the title and scope of all 55 rulebooks; every rulebook that matches is picked, and older rulebooks replaced by newer ones are dropped. Then one Claude agent reads every rule that says something "shall" be done in the picked rulebooks and answers yes or no for this product. Its weakness: the patterns also catch a few rulebooks that do not apply, so the agent must reject their rules.

1. Regulation selection: `regselect` `llm_regex`: `claude-opus-5-5` gets only `spec.md` and returns 6-20
   case-insensitive regexes for the product's functions, components, installation and electronics (generic words
   forbidden); invalid regexes are dropped; each regulation whose title + paragraph 1 scope matches any pattern is
   selected; then the supersession and vehicle-category filters. Cached per spec in `devansh-toolkit/.cache`.
2. Candidates: every clause of the selected regulations in `data-ingestion/clauses` matching `\b(shall|must)\b`.
3. Classifier: single agent, `claude-opus-5-5` effort medium, structured output, batches of 40, cached per batch
   (the devansh-llm-clause-filter prompt).
4. Output: every kept clause as one requirement; no size cut.

Inputs: the case's `spec.md`. Output: `outputs/predictions.json`.
Config: `config.json`. Code: `../devansh-toolkit/src/retrieval` (`regselect.py`, `classify.py`, `export.py`).

## Run

```bash
cd approaches/experiments/devansh-toolkit/src      # after ../setup.sh; needs ANTHROPIC_API_KEY or a git-ignored .env
../.venv/bin/python -m retrieval.export --config ../../devansh-dynregex-llm-clause-filter/config.json --out ../../devansh-dynregex-llm-clause-filter/outputs/predictions.json
cd ../../../..
python approaches/benchmarking/bench.py devansh-dynregex-llm-clause-filter approaches/experiments/devansh-dynregex-llm-clause-filter/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

LLM answers are cached in `devansh-toolkit/.cache/` (git-ignored): re-runs are free and repeatable, fresh runs vary.

## Result (dev-rear-lamp, team bench)

See `results.json` and the dashboard (page, clause and regulation F2).

## Assumptions and limitations

- Regulation selection is generated per spec by the LLM (no hand-written product rules), so it should transfer better than the rules-based variants; the regex prompt was not tuned against dev scores.
- Declared dev tuning: classifier prompt gives lighting examples (headlamps, direction indicators) seen in the dev domain.
- Requirement text is the raw clause, not yet split into single obligations.
