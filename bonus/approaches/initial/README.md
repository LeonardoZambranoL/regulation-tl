# Bonus change impact: exhaustive pipeline

This experiment implements the Certivity regulatory change impact subgoal for UN R175 version 0.1.0 → 1.0.0. The default pipeline records a decision for every old requirement, automatically retaining clearly unchanged requirements and assigning changed or uncertain cases to Claude. Every new clause receives a bounded Claude obligation-extraction task. The submission preserves old requirement IDs and uses the official `{team_id, case_id, changes}` format.

## Contract

The allowed change kinds are `modified`, `removed`, and `added`. Modified/removed entries use an existing requirement ID; added entries use `requirement_id: null`. Modified/added entries include `new_text` (at most 2,000 characters) and a new-version source citation; all entries include a reason. Removed entries omit the source instead of emitting `source: null`. The official schema and validator are in the sibling `industrial-ai-hackathon` repository. There is no official local subgoal scorer; the bundled benchmark is a diagnostic proxy.

## Pipeline

The old regulation text and clauses reuse `data-ingestion/text/` and `data-ingestion/clauses/`. A new PDF is passed through the shared `pdf_to_txt.py` and `txt_to_clauses.py` once per PDF SHA and cached under this experiment.

Discovery uses two independent, deterministic worklists:

1. **Existing requirements:** find each requirement's old source clause and its unique same-paragraph counterpart. Automatically mark the requirement unchanged when the source text matches after whitespace normalization and the dependency checks below pass. Send changed or uncertain requirements to Claude in batches of ten, with up to five ranked new matches and up to five explicitly referenced clauses from each version. Every old ID receives exactly one `unchanged`, `modified`, or `removed` decision, whether automatic or model-generated. Unchanged decisions are retained in the audit and omitted from the submission.
2. **New obligations:** assign all 223 new-version clauses to batches of six. Each clause receives up to four old matches selected using paragraph identifiers and fuzzy text similarity. Claude extracts atomic obligations and classifies them as `existing`, `modified_existing`, or `new`. Only `new` obligations become added entries; every clause must have a result, including an empty obligation list when appropriate. This includes new obligations inserted into an existing paragraph.

The shortcut preserves punctuation, case, values and units; only whitespace is normalized. It checks the original source page, parser review flags, numbered parent clauses, and recursively resolved paragraph/section/table/annex references, including children of referenced sections. It also checks changed definitions in R175 section 2 for terms used by the requirement and its dependencies. Missing, ambiguous, grouped or relative references, changed dependencies, and unresolved changed definitions require Claude review. This is a conservative textual check, not a proof that every implicit legal dependency is unchanged.

Track A also searches sentences and list items across both parsed documents using the requirement text. It retains two old evidence blocks and three new evidence blocks, including neighboring text and source metadata. This recovers an obligation when a parser boundary placed it in a table or other block. New evidence scores also contribute to ranking the five new-clause candidates. Each candidate obligation pair receives a word-level diff that preserves qualifiers, punctuation, numbers and units. Claude must identify relevant wording edits and explain any decision to treat them as unchanged; changed target-selection or applicability modifiers must be considered even when the main action remains the same. Named tables and annexes join the explicit referenced context. The evidence and comparisons are saved in the alignment audit.

Preflight reports the automatic-unchanged count and remaining Claude review count separately. The request count is `ceil(remaining old requirements / 10) + ceil(new clauses / 6)`; the 223 new clauses still require 38 batches. Calls run sequentially. Added entries are deduplicated by normalized text equality. The unified diff and legacy candidate counts remain inspection artifacts; the legacy selector does not determine which old requirements receive a decision or which new clauses are inspected.

Each batch is cached by model, full prompt, and local schema hash. The Anthropic request uses a compatible structural schema; numerical and string limits are described to Claude and enforced locally with the full schema. Valid cached responses must also cover exactly the assigned IDs. Recoverable failures receive up to three application-level attempts, with validation feedback when applicable; permanent HTTP 4xx errors such as 400 are not retried. Citation-to-clause checks, ID checks, and the official submission schema gate output. The full alignment and decisions are retained in `outputs/assessment-<case>-exhaustive.json` for miss diagnosis. Claude Sonnet 5.5 is the configured model.

Preflight estimates batch count, tokens, cost, and runtime before model requests using the current batch sizes. Costs use the configured token rates, and API usage is logged as calls finish. A resumed run reuses valid batch caches; its printed spend covers new calls in that invocation. Changing batch sizes changes the corresponding prompt hashes, so earlier Track A batches will not be reused with the new size.

`--ablation all` runs the deterministic `text`, `semantic`, and `crossref` baselines, the prior diff-driven `agent`, and `exhaustive`, then writes a comparison. The legacy agent can reuse its checkpoint and retains its separate smoke-check behavior. This mode can make more API calls than the default exhaustive run. `--ablation llm` is an alias for `exhaustive`.

Citation recovery also accepts list-item ranges such as `6.6.1.2 (a)-(b)` (including en/em dashes or `to`). It checks the cited page, parent paragraph, and every item in the range in source order before normalizing to the parent paragraph. Reversed, mixed-type, or unsupported ranges remain errors. This assembly fix does not change model prompts or invalidate cached responses; rerun the normal command to reuse the current prompt's completed batches without choosing between older cache generations.

## Scope-aware addition matching

Omitted annex prefixes are also resolved for list-item, range and table-row citations by applying the existing suffix checks to the local paragraph number, then restoring the unique full source label. Item markers must still exist in the source and the cited page must belong to that clause.

For annex citations that omit their enclosing labels (for example, a bare paragraph number), assembly restores the full annex/appendix path only when the provided source clauses and cited page identify exactly one matching paragraph. Ambiguous or unsupported citations remain errors. Original citations are retained in the normalization audit. This assembly-only correction leaves model caches valid.

Assembly accepts table-row citations such as `7.2.3.1 Table 1 item 10` and dotted subitems. It requires the cited page to belong to the source clause, the named table to appear there, and the numbered row to occur after the table label. The submission uses the parent paragraph and retains the original detailed citation in the audit. This does not change prompt hashes; completed model responses remain reusable. Page checking is at parsed-clause granularity for tables spanning several pages.

Track B now includes numbered parent provisions for each new clause and its old candidates, plus whether the new paragraph number existed before. Repeated actions in a separately introduced procedure or applicability context must remain separate additions. Matching wording alone cannot justify `existing` or `modified_existing`: Claude must identify an old clause and explain continuity of scope. Genuine relocations and renumbering can still match old obligations. Uncertain equivalence is retained as an addition with the uncertainty explained, which may increase false positives.

Addition deduplication now requires both normalized text and the same paragraph/page citation; equal text in different clauses is preserved. This supersedes the text-only deduplication described above. The change was motivated by dev diagnostics, uses no hard-coded answer clauses, and has not been run or benchmarked. It changes Track B prompt hashes, so a normal run redoes those batches while reusing unchanged Track A caches. Use the normal run command, not `--assemble-only`, to obtain the new classifications.

## Run

Deterministic alignment, candidate discovery and exhaustive review worklists are cached under `.cache/preparation/<case>/`. Keys include the actual parsed documents, requirement inventory and relevant source files; changed inputs/code cause recomputation. Writes are atomic, and unreadable caches are rebuilt. Startup prints progress and cache-hit messages. The first run after this change creates these caches; subsequent runs reuse them. Execution also reuses the preflight worklist instead of computing it a second time. Model response cache keys are unchanged. This change has not been run during implementation.

### Held-out regulation-change case

The `heldout` configuration uses UN R171 base 1.1.0 and latest 2.0.0, with `case_id: subgoal-heldout`. Inputs are `data/subgoal/heldout/old.pdf` and `new.pdf` (verified against the official case manifest), and the sibling challenge's `subgoal/heldout/requirements_old.json`. It reuses shared R171 base text/clauses; the new PDF is parsed once on first execution. No held-out run has been performed during configuration.

```powershell
python bonus\approaches\initial\run.py --case heldout --estimate-only
python bonus\approaches\initial\run.py --case heldout
```

Upload `bonus/approaches/initial/outputs/heldout/subgoal-heldout.json` after the run completes. All held-out outputs, audits and logs go in `outputs/heldout/`; model caches use `.cache/exhaustive/heldout/`, and parsing caches are keyed by PDF hash. Dev outputs stay in their existing location. There is no public held-out answer, so local evaluation is skipped when `expected.json` is absent. The first estimate command performs local ingestion but makes no model calls.

Track B now inventories independent procedure steps, operating cases, and mandatory actions or permissions in an internal `coverage` list. Each included unit maps to exactly one distinct obligation; each excluded unit needs a reason. Shared conditions and exceptions stay with their obligation and are repeated when independent cases are split. Local validation checks index bounds, unique mappings, and complete coverage of extracted entries; failed checks use the existing bounded correction retries. This checks the model's inventory, not proof that it found every source obligation. The coverage list is saved in the audit, never in the submission.

This atomization change invalidates Track B caches through the schema/prompt hash. Run normally to generate new addition reviews; old Track A responses remain reusable. Do not use `--assemble-only` with the pre-change Track B caches. No generation or benchmark has been run for this change. Benchmark diagnostics now resolve audit subpoint citations via clause IDs and distinguish a missing match caused by an output entry already matched elsewhere from an omitted obligation; scoring itself is unchanged.

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe bonus\approaches\initial\run.py --case dev --estimate-only
.\.venv\Scripts\python.exe bonus\approaches\initial\run.py --case dev
```

Set `ANTHROPIC_API_KEY` in the process environment or the git-ignored root `.env`. The final file is `outputs/subgoal-dev.json`; the script validates it before writing. `outputs/assessment-dev-exhaustive.json` contains every per-requirement decision and every extracted clause obligation. `outputs/usage-exhaustive-subgoal-dev.jsonl` logs model usage and estimated cost. Restarting reuses completed batch caches.

If every batch completed but final assembly failed, finish from the saved responses without API calls:

```powershell
.\.venv\Scripts\python.exe bonus\approaches\initial\run.py --case dev --assemble-only
```

Assembly-only checks the saved preflight PDF hashes and model, validates cached response schemas, and requires complete, unambiguous cached coverage of the requirements still needing model review and every new clause. It applies current automatic-unchanged decisions instead of cached model decisions for eligible IDs. It can assemble earlier batches of five after the default has changed to ten. Missing or conflicting required cached reviews stop assembly without requesting replacements from Claude. The input case and parsed text must still correspond to that cached run.

To apply an improved Track A prompt, use the normal run command: changed prompt hashes cause new existing-requirement reviews, while unchanged Track B prompts reuse their cached responses. `--assemble-only` cannot apply new model reasoning to previously cached decisions.

Citation validation accepts a list-item suffix such as `6.6.1.2(c)` when the cited page belongs to paragraph `6.6.1.2` and `(c)` exists in its text. The submission uses the parser's parent paragraph, and the assessment records the original citation under `citation_normalizations`. Unsupported suffixes or pages still fail validation.

All output paths below are relative to `bonus/approaches/initial/`:

| File | Contents |
| --- | --- |
| `outputs/subgoal-dev.json` | Submission from the latest successful default/exhaustive run |
| `outputs/subgoal-dev-exhaustive.json` | The same submission with its approach label |
| `outputs/preflight-dev.json` | Input hashes, coverage and estimates |
| `outputs/alignment-dev-exhaustive.json` | Requirement/clause alignment and retrieval scores |
| `outputs/assessment-dev-exhaustive.json` | All model decisions, extracted obligations, token totals and runtime |
| `outputs/evaluation-dev-exhaustive.json` | Category-level local metrics and missed-change diagnoses |
| `outputs/usage-exhaustive-subgoal-dev.jsonl` | Appended API usage records |
| `outputs/ablation-dev.json` | Comparison produced by `--ablation all` |

After generation, the script reads the dev answer only for evaluation. The report separates modified, removed, and added precision/recall, and uses the assessment audit to explain missed changes where possible. Added matches require matching citations and token F1 of at least 0.45, with one-to-one matching. This is not the platform's semantic judgment. A failed run leaves any older submission file in place; use the final `Submission:` message to confirm the current run finished.

## Previous diff-agent result

The prior single-agent pipeline produced a valid schema submission but did not provide exhaustive coverage: the local diagnostic matched 6/7 old impacts and 8/17 expected additions. Initial attempts to run the exhaustive rewrite encountered schema syntax and API-schema compatibility errors; those code issues were corrected. No completed exhaustive evaluation is documented here yet. Dev results remain optimistic and must not be treated as unseen-case performance.

## Limits

- Fuzzy alignment is lexical and can miss semantically distant renumbered clauses; each batch gives the classifier multiple matches and referenced provisions.
- The current implementation has no embedding retrieval, separate old-version atomic extraction pass, or semantic deduplication pass. Claude compares new obligations with retrieved old clause text.
- The shortcut traverses explicit resolved references and numbered parents, with a definition-term check for R175 section 2. Implicit dependencies and applicability changes elsewhere can still escape detection. Claude's supplied reference context remains capped at five clauses per version.
- Supported configurations are R175 dev and R171 heldout. Further cases require a case configuration, matching shared base text/clauses and case PDFs.
- The model’s atomic obligation boundaries may differ from the answer key even when the meaning is covered.
- Extracted text can lose complex table relationships and cannot represent visual-only content.
- The official score is the authority; the local added-obligation matcher is only a proxy.
