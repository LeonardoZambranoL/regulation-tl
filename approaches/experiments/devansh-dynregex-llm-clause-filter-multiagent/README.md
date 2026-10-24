# devansh-dynregex-llm-clause-filter-multiagent

Owner: Devansh. **Claude writes regex patterns from the spec to pick the regulations, then three Claude agents check each other on every "shall" clause.** Compare with devansh-dynregex-llm-clause-filter (same selection, one agent).

## What it does and how it works

Nothing is hand-written for the product. Claude reads only the product description and writes search patterns for its functions and parts; every rulebook whose title and scope match is picked. Then three Claude agents check each other's work so that no applicable rule is missed. Agent A is a strict engineer: it keeps a rule only if it clearly applies to this product. Agent B is a completeness auditor: it keeps every rule that could apply and only drops clear misses. When A and B disagree, agent C, a senior adjudicator, reads the rule and both verdicts and makes the final call. Rules both keep are handed in, rules both drop are left out. Its weakness: it is the most expensive variant (three agents over more rulebooks).

1. Regulation selection: `regselect` `llm_regex` (spec-only regexes from `claude-opus-5-5`, matched against
   every regulation's title + scope, then supersession and vehicle-category filters), as in devansh-dynregex-llm-clause-filter.
2. Candidates: every clause of the selected regulations in `data-ingestion/clauses` matching `\b(shall|must)\b`.
3. Multi-agent review (`classify.classify_multi`), all `claude-opus-5-5` with structured JSON output, batches of
   40 clauses (25 for the adjudicator), 6 parallel requests, cached per batch:
   - Agent A, strict applicability (the single-agent prompt, effort medium);
   - Agent B, completeness auditor ("answer true unless clearly not applicable", effort medium);
   - Agent C, adjudicator (effort high), only for clauses where A and B disagree, sees both verdicts.
   Final: A = B -> that verdict; A != B -> C's verdict. Agreement counts are in `outputs/review-report.json`.
4. Output: every kept clause as one requirement; no size cut.

Inputs: the case's `spec.md`. Output: `outputs/predictions.json`.
The multi-agent review also writes `outputs/review-report.json` (how often the agents agreed).

Config: `config.json`. Code: `../devansh-toolkit/src/retrieval` (`regselect.py`, `classify.py`, `export.py`).

## Run

```bash
cd approaches/experiments/devansh-toolkit/src      # after ../setup.sh; needs ANTHROPIC_API_KEY or a git-ignored .env
../.venv/bin/python -m retrieval.export --config ../../devansh-dynregex-llm-clause-filter-multiagent/config.json --out ../../devansh-dynregex-llm-clause-filter-multiagent/outputs/predictions.json
cd ../../../..
python approaches/benchmarking/bench.py devansh-dynregex-llm-clause-filter-multiagent approaches/experiments/devansh-dynregex-llm-clause-filter-multiagent/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

LLM answers are cached in `devansh-toolkit/.cache/` (git-ignored): re-runs are free and repeatable, fresh runs vary.

## Result (dev-rear-lamp, team bench)

See `results.json` and the dashboard (page, clause and regulation F2).

## Assumptions and limitations

- No hand-written product rules (spec-generated regex selection); the multi-agent review adds recall.
- Declared dev tuning: reviewer prompts give lighting examples (headlamps, direction indicators) seen in the dev domain.
- Requirement text is the raw clause, not yet split into single obligations.
