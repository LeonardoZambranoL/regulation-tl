# devansh-llm-clause-filter

Owner: Devansh. **Rules-based regulation selection, then an LLM decides clause by clause what applies.** No retrieval
ranking and no size cut.

1. Regulation selection (`regselect`, method `combined` = rules): spec keywords -> regulation families, then
   supersession and vehicle-category filters. Dev case: R48, R148, R150, R10 (exactly the gold set).
2. Candidates: every clause of those regulations containing "shall" / "must" in `data-ingestion/clauses`
   (1,240 on the dev case).
3. Classifier (`classify.py`): `claude-opus-5-5`, effort `medium`, structured JSON output, batches of 40 clauses,
   6 in parallel. The prompt states which clause kinds apply (construction, marking, photometry and colour, tests,
   installation of the product's functions, general requirements, EMC for electronics) and which do not (functions the
   product lacks, other vehicle categories, definitions, authorities' administrative duties, scope statements).
4. Output: every kept clause as one requirement (clause text, cited at first page + paragraph). 308 kept on the dev case.

Code lives in `../devansh-toolkit/src/retrieval` (shared by all devansh-* experiments). Config: `config.json`.

## Run

```bash
cd approaches/experiments/devansh-toolkit/src        # after ../setup.sh; needs ANTHROPIC_API_KEY or a git-ignored .env
../.venv/bin/python -m retrieval.export --config ../../devansh-llm-clause-filter/config.json --out ../../devansh-llm-clause-filter/outputs/predictions.json
cd ../../../..
python approaches/benchmarking/bench.py devansh-llm-clause-filter approaches/experiments/devansh-llm-clause-filter/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

Classifier answers are cached per batch in `devansh-toolkit/.cache/` (git-ignored); the first run costs about 31 API calls.
Not deterministic across fresh runs (LLM); cached runs are repeatable.

## Result (dev-rear-lamp, team bench)

| page P | page R | page F2 | reg F2 | requirements |
|---|---|---|---|---|
| 0.542 | 0.981 | **0.844** | 1.000 | 308 |

## Known gaps / next ideas

- 308 kept vs 190 gold: precision is the gap. Try effort `high`, a second "is this a separate obligation?" pass, or
  excluding test-procedure annex detail.
- Requirement text is the raw clause. The platform's requirement-level score needs one obligation per requirement:
  split kept clauses into obligations with the LLM (same citation).
- Only one dev case: the held-out product will test whether the prompt generalises.
