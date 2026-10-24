# Exhaustive Clause Analysis

An exhaustive agentic experiment: concurrent Claude workers inspect every input
record, use native tools to investigate context, propose obligations, and verify them.
No embeddings, database, or reference graph. Never reads `expected.json`.

## Setup

From the repository root (Python 3.12+):

```powershell
.\.venv\Scripts\python.exe -m pip install -r approaches/experiments/exhaustive-clause-analysis/requirements.txt
```

Add your **Claude** key to the repository-root `.env`:

```dotenv
ANTHROPIC_API_KEY=your-anthropic-key
```

The Voyage key is separate. Existing environment variables override `.env`.
Dependencies are pinned in this experiment's requirements file. Model and worker
settings are in `config.json`; prompts are in `prompts.py`. Assessment uses
`model: claude-haiku-5-5`; verification uses `verification_model: claude-sonnet-5-5`.
Both stages keep their own model throughout tool calls. Change these settings
if your account does not have access. Cached responses are separated by model.

## Run

Check distribution without an API key, network calls, or output writes:

```powershell
.\.venv\Scripts\python.exe approaches/experiments/exhaustive-clause-analysis/run.py --dry-run
```

Start with a small **paid** smoke test, writing to its own output folder:

```powershell
.\.venv\Scripts\python.exe approaches/experiments/exhaustive-clause-analysis/run.py --only "UN R148" --max-batches 2 --output approaches/experiments/exhaustive-clause-analysis/smoke-output
```

Full experiment, including the optional product image:

```powershell
.\.venv\Scripts\python.exe approaches/experiments/exhaustive-clause-analysis/run.py --image ../industrial-ai-hackathon/cases/dev-rear-lamp/exploded_view.png
```

Defaults read `data-ingestion/clauses/*.json`, the spec at
`../industrial-ai-hackathon/cases/dev-rear-lamp/spec.md`, and the challenge's
`regulations/index.json`. Only indexed base versions are accepted. Every JSON
record is assigned, including tables, headings, and introductions. `--only` and
`--max-batches` explicitly create a subset run, marked partial in diagnostics.
Image input is optional and sent with assessment and verification requests; do
not assume the model saw an image unless `--image` was used.

The team ID defaults to `4TL`; override it with `--team-id NAME`.

For another case, set `--spec PATH --case-id CASE --image PATH` as appropriate.
Other options: `--clauses PATH`, `--index PATH`, `--config PATH`, `--output PATH`.
Relative CLI paths resolve from your working directory; defaults resolve from
the script location. A sibling challenge checkout is needed for default inputs.

## Method

1. Partition consecutive records within each regulation into bounded batches.
   Include available parent clauses, scope clauses, and neighbours as context.
   Context omitted by the character budget is identified explicitly.
2. Run up to ten concurrent Claude requests (configurable). Each target must
   be assessed only by its assigned worker. Every proposal must cite the same
   target as its enclosing decision; Python rejects cross-clause proposals.
   Neighbouring and tool-retrieved clauses provide interpretation context only.
   Each target must
   receive exactly one `relevant`, `irrelevant`, or `needs_context` decision,
   with a short explanation and confidence. Relevant context can emit zero
   requirements; clauses with several obligations can emit several.
3. Claude chooses when to call native `search_clauses` and `read_clause` tools.
   Python executes them locally and returns `tool_result` messages in the same
   conversation. Search returns up to eight label/keyword matches with snippets;
   read fetches full source text in character-limited chunks. Both tools paginate.
   Search snippets are discovery aids, not eligible citation evidence by themselves.
   Each assessment or verification agent gets up to `max_tool_rounds` (default 4)
   and `max_tool_calls` (default 8). It may finish early without tools. Once the
   budget is exhausted, tool use is disabled and Claude must return final JSON.
   Insufficient evidence stays `needs_context` (assessment) or `unresolved`
   (verification). Missing product facts are never invented.
4. Check that source quotes and spec quotes actually occur in the supplied text.
   Page selection must belong to the cited clause's pages. Independently ask
   Claude to verify candidates; only `supported` candidates enter the submission.
   Verification workers have the same native tools. Unsupported/unresolved
   candidates remain in diagnostics with reasons.
5. Python assigns submission IDs and attaches regulation/version/paragraph from
   the original clause records. It runs the **bundled official validator**, in
   strict mode with the challenge index, and checks the 5 MiB limit before export.

The API uses structured JSON outputs plus local checks for completeness, quoted
evidence, confidence ranges, valid sources, and IDs. Calls that fail validation,
rate limits, or transient API errors retry twice. Invalid final answers receive
up to two corrective turns; these cannot reset the tool budget. Permanent authentication or
access errors fail the attempt.

If an assessment or verification batch still fails, the whole batch is retried
up to `batch_retries` times (default 2: three attempts total), after delays of
2 and 4 seconds. The batch occupies one worker during its retry delay. Progress
advances once, after the batch succeeds or exhausts its attempts; recovered
batches are not counted as failures. Diagnostics records each batch attempt.
Retries use separate cache keys so an invalid cached answer is not replayed as
its own retry. Those new API calls are included in cost estimates. Successful
batches are not rerun. The final exit code is nonzero if batches remain failed.

## Outputs

Three output files in `outputs/` (or `--output`):

- `submission.json`: only `team_id`, `case_id`, and schema-compatible requirements.
  Requirement `text` contains the obligation alone.
- `diagnostics.json`: per-clause decisions, explanations, uncalibrated confidence,
  outstanding context requests, tool names/arguments/results, per-turn usage,
  evidence, verification, candidate
  to submission ID mapping, coverage, errors, configuration, runtime version,
  timestamps, and reported API token usage. Cached usage describes the original
  request, not a new charge. Confidence is never used as a filtering threshold.
- `costs.json`: a small cost report for this invocation, split into assessment and
  verification, with token counts, local cache hits, and estimated total USD.
  Updated after every API response, so partial costs survive interruption.

Completed API turns are cached under the Git-ignored `.cache/` directory beside
the script. Request fingerprints include the full conversation, tools, model,
prompt, schema, spec/image, and a fingerprint of the entire clause corpus.
Reruns replay cached turns, execute the read-only tools, and revalidate results.
Changes to any corpus text invalidate cached tool-driven conversations.
Final outputs are regenerated; cache files are internal resume data, not extra
submission files. The API does not use a random seed here; diagnostics records
`seed: null`. Results are not guaranteed deterministic on fresh calls.

Partial runs can still produce schema-valid submissions: **check diagnostics
coverage and errors before submitting**. Schema validation checks format, not
semantic accuracy. On final validation failure only diagnostics is updated;
an older submission file, if present, is not the result of that failed run.

## Limitations

Source clause splits are provisional. Text-only table errors and superscripts
are not repaired here. Product-image observations cannot be checked by string
matching. A multi-page clause's chosen page is checked against its page list,
not an exact quote-to-page map. Context retrieval is bounded and can miss
definitions/references; unresolved results stay visible. All supported matches
are retained, including repeated obligations. Exhaustive clause assignment does not guarantee exhaustive or correct requirements.

Full runs involve thousands of requests plus agent tool turns and verification. Review a smoke test before running the entire corpus.

The terminal shows separate assessment and verification progress bars, including
completed batches, percentage, elapsed time, estimated remaining time, and failure
counts and the running estimated total cost in USD. Assessment also shows successful batches; verification shows supported
requirements. Bars advance when a batch finishes (including its tool calls),
not on every API turn. Failed batches count as finished and are clearly reported.

## Benchmarking

```powershell
.\.venv\Scripts\python.exe approaches/benchmarking/bench.py exhaustive-clause-analysis approaches/experiments/exhaustive-clause-analysis/outputs/submission.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

Benchmarking is a separate step
and never feeds golden requirements to workers. The local score evaluates
regulation/page coverage, not semantic requirement correctness.

API implementation references:
https://platform.claude.com/docs/en/build-with-claude/structured-outputs
https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls

## Cost estimates

`pricing.json` contains USD rates per million tokens for each model. Rates were
checked on 2026-10-24 against:
- https://platform.claude.com/docs/en/models/haiku-5-5/overview
- https://platform.claude.com/docs/en/models/sonnet-5-5/overview
- https://platform.claude.com/docs/en/models/opus-5-5/overview

Costs use the API's input/output usage and any server-side prompt cache usage.
Haiku's higher rates apply when a request exceeds 100,000 total input tokens,
including cache reads and writes; output tokens do not count toward this threshold.
Tool turns and responses that later fail validation are counted. Replaying a
local cached response adds zero new cost. Bars update after each completed batch;
`costs.json` updates after each API response, including intermediate tool turns.
The terminal also prints the total at the end. Rerunning starts a new cost report
for that invocation; copy the prior report if you want to keep its history.

Estimates are not invoices: discounts, credits, taxes, and requests for which no
usage was received are not included. Network failures and server errors without
usage are flagged as `unpriced_requests`; they may have incurred charges. Update
rates when pricing changes or when selecting another model. This is cost tracking,
not a spending cap.
