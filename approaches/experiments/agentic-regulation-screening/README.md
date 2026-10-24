# Agentic regulation screening

This experiment does not use embeddings, LanceDB, or Gemini. One Opus agent is assigned to each regulation/version. It reads that regulation's scope and first eight clauses, may continue sequentially, search within the regulation, or open any clause, and decides whether a complete review is worthwhile. Every clause in selected, uncertain, or failed-to-screen regulations is then assessed by Sonnet workers and independently verified by Sonnet.

## Run

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r approaches/experiments/agentic-regulation-screening/requirements.txt
python approaches/experiments/agentic-regulation-screening/run.py --dry-run
python approaches/experiments/agentic-regulation-screening/run.py
```

Only `ANTHROPIC_API_KEY` is required in the repository `.env` or this experiment's `.env`. The default specification is `../industrial-ai-hackathon/cases/dev-rear-lamp/spec.md`, the team ID is `4TL`, and the case ID is `dev-rear-lamp`.

Useful commands:

```powershell
# Run only regulation screening and inspect screening.json.
python approaches/experiments/agentic-regulation-screening/run.py --screen-only

# Small paid plumbing run; it is deliberately incomplete and exits nonzero.
python approaches/experiments/agentic-regulation-screening/run.py --max-regulations 2 --max-batches 2

# Another product and isolated output directory.
python approaches/experiments/agentic-regulation-screening/run.py --spec path/to/spec.md --case-id example --output path/to/output
```

## Method

1. Load all base-version clause JSON files permitted by the challenge index. No answer key is read.
2. Launch one independent `claude-opus-5-5` screening task per regulation, with ten tasks in parallel. The initial prompt contains the regulation title, identifiable scope clause, and first eight clauses in source order, bounded to 40,000 characters.
3. Each screening agent can call `continue_reading` for up to ten subsequent clauses at a time, `search_regulation` for lexical discovery within its assigned regulation, and `read_clause` for an arbitrary clause ID or continuation of a long clause. It has up to six tool rounds and twelve calls. Tools cannot access another regulation during screening.
4. The agent returns `select`, `reject`, or `uncertain`, with a reason, confidence, exact specification evidence, and topics for review. Only an explicit `reject` removes a regulation. `uncertain` regulations and screening failures are included to protect recall. A failed screening still makes the run incomplete and visible in diagnostics.
5. Split all clauses in retained regulations into batches of at most twelve clauses and 14,000 target characters. Ten parallel Sonnet workers assess each clause exactly once. They receive the product specification, parent/scope/neighbor context up to 24,000 characters, and cross-corpus lexical search/read tools. Each worker may propose only obligations from its assigned target clauses.
6. Independently verify proposed requirements with Sonnet. Export only supported candidates. Do not deduplicate requirements. Validate the official schema and source index.

Every API/validation task can retry twice after its first failure. Claude response caching is local to this experiment. Progress bars show completed screening, assessment and verification work with the live estimated Claude cost.

## Outputs

- `screening.json`: every regulation decision, reasoning, confidence, tool trace, selected union, and failures.
- `predictions.json`: only schema-compatible supported requirements.
- `diagnostics.json`: detailed clause decisions, verification, coverage and errors.
- `costs.json`: estimated screening, assessment and verification Claude cost for this invocation.

Screening reads only enough of each regulation to decide whether the expensive full scan is worthwhile. Its main risk is rejecting a relevant regulation based on incomplete reading. The prompt sets a conservative rejection rule, exposes tools for further reading, and includes uncertain or failed cases, but it cannot eliminate false negatives. Full selected-regulation coverage does not prove all relevant regulations were selected.

## Results

Dev `dev-rear-lamp` run (`37ec3cfc2ef94836ade4be35cadc585d`): Opus screened all 56 regulations, selected 9, and Sonnet assessed all 5,107 selected clauses without errors. Verification exported 616 requirements at an estimated total API cost of $21.7112.

- Page: precision 0.3355, recall 0.9623, F1 0.4976, F2 0.7005 (51/53 expected pages matched; 152 submitted).
- Clause: precision 0.1412, recall 0.6860, F1 0.2341, F2 0.3871 (83/121 expected clauses matched; 588 submitted).
- Regulation: precision 0.4444, recall 1.0000, F1 0.6154, F2 0.8000 (4/4 expected regulations matched; 9 submitted).

The current dev page-F2 leader is `devansh-llm-clause-filter` at 0.8442, with clause F2 0.6195 and regulation F2 1.0000. This experiment trails it by 0.1437 page F2, 0.2324 clause F2 and 0.2000 regulation F2. Its strong recall and low precision show that conservative regulation screening retained the correct regulations but downstream clause selection overproduced citations. No holdout run exists, so the dashboard cannot calculate a robust score. No gold data entered generation and no parameter was selected from this score.
