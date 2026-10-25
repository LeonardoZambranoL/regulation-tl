# jojo-source-repair-v2

New experimental strategy: repair unsupported claim scope and missing conditions using the cited regulation, preserving every requirement, ID and citation. This changes substantive requirement text; it is not a copy of the previous 546-item output. The previous candidate remains the fallback.

**New output:** `outputs/submission-heldout-front-bumper.json`, **546 requirements with 12 repaired texts**. Strict validation passed. Dev has6 repairs among206 items; ACPE has4 among163. Every ID, citation and item order is unchanged. The new bumper SHA-256 is `cef6a1ee3a8a8fe68793c85d6bf3ac15d10ed411aed58cf1a6fe8f141f62fc94`.

## Frozen decision rule

Before benchmarking, review a requirement with its same-paragraph siblings and the actual local source, including referenced tables and parent conditions. Repair only an objectively unsupported value/operator/subject or a missing source condition that makes the standalone obligation broader or unintelligible. Preserve separate obligations, permissions and exceptions. Do not delete optional features merely absent from the product description, administrative clauses, near-duplicates or cross-regulation counterparts. No pruning or quantity cap is permitted in this strategy.

Twelve rules in `rules.json` are fixed before execution and new gold measurement. Important example: the source's 4 cd minimum for front position lamps applies on the reference axis, whereas the inherited text applies it to the entire standard light distribution. Other changes restore the built-in-system marking exemption, conditional extra module-code symbols, the six-second ACPE initialisation trigger, and the missing subject of a GTR9 static-test permission. The audit is targeted at potential source defects, not a claim to have exhaustively reviewed every obligation.

The strategy was pushed as22c7f3f before the first run. Reviewing its exact diff exposed one overly broad predicate: an already-correct dev module-code condition was unnecessarily rewritten. The final predicate skips text already conditional on several non-identical modules. This correctness fix was based on source and output review, not benchmark outcomes; both cases were rerun afterward.

## Reproduce

From repository root, Python 3.12+ with jsonschema installed:

```sh
python approaches/experiments/jojo-source-repair-v2/run.py
python approaches/experiments/jojo-source-repair-v2/bench.py
python approaches/experiments/jojo-source-repair-v2/verify.py
python ../industrial-ai-hackathon/tools/validate.py approaches/experiments/jojo-source-repair-v2/outputs/submission-heldout-front-bumper.json --index ../industrial-ai-hackathon/regulations/index.json --strict
```

The strategy code and frozen rules are committed/pushed before running to generate the new outputs, as requested. Then both labelled cases are benchmarked and results committed/pushed. `inputs.json` pins the three inherited files. `run.py` does not read gold or credentials. It resolves evidence using regulation, normalized paragraph **and page** to avoid confusing GTR9 rationale paragraphs with its technical text. The output ledger records exact before/after text, source excerpts and source-file hashes.

Benchmarks use the unchanged shared evaluator and its supported isolated output root so only this experiment folder changes. The folder-specific pre-commit hook preserves the user's explicit folder-only scope and checks staged scope/secrets; output commits also verify official schemas, exact edit boundaries, evidence hashes and both current benchmark fingerprints. The standard repository pre-push hook remains active.

## Scoring and limitations

| Case | Items / repaired | Page F2 | Clause F2 | Regulation F2 |
| --- | ---: | ---: | ---: | ---: |
| dev-rear-lamp |206 /6|99.6241%|98.3740%|100%|
| holdout-acpe |163 /4|72.7273%|79.5796%|83.3333%|

All citation metrics equal the previous candidate because citations are intentionally unchanged. Full precision/recall/F1/F2 and both input fingerprints are in `benchmark-summary.json`; the unseen-case consistency check says up to date. `verify.py` additionally passed three official schemas, exact edit-boundary checks, source evidence hashes and both current prediction fingerprints. There is no newly measured requirement-level score to compare with the live platform leader77.4%.

The prior 546-item candidate is associated with the current platform F2 **63.1%** (174 matches inferred against208 expected), above the original62.8% baseline. This new candidate has **no measured platform or semantic-judge score**. Because the count stays546, each gained/lost match changes F2 by approximately0.363 percentage points. If matches remain174 its F2 stays63.14%;173 gives62.77%;175 gives63.50%. These are scenarios, not forecasts. Source correctness alone does not prove the platform will count more matches.

Hard paid-API budget and spend are both$0; no own API key is configured, no teammate key is accessed, and no paid judge runs. This is an experimental candidate explicitly requested after the unchanged conservative output; it does not satisfy an empirically established semantic-improvement gate. The dev pipeline is inherited and dev-tuned; risk is high. Answer keys are used only by `bench.py` for citation scoring. Citation scores cannot measure wording improvements.

No platform upload is performed. Upload the new file if testing this strategy; if it scores below the best platform result, restore `../jojo-final-bumper/outputs/fallback-heldout-front-bumper.json`. Only the last upload counts; observe the live five-per-hour limit and reserve restoration capacity.
