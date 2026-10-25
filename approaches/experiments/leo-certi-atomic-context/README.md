# leo-certi-atomic-context

Owner: Leo. Isolated source fork of `certi-pipeline`, aimed at improving requirement F2 through better obligation boundaries and product applicability. The base experiment is unchanged. This variant has NOT been run or benchmarked; `outputs/predictions.json` is an empty placeholder, not a submission.

## What changed

- Sonnet 5.5 for all model stages, two concurrent workers, extraction and verification batches of at most eight items (extraction also retains the 14,000-character batching bound).
- Complete assigned clause text instead of 6,000/3,500-character truncation. Same-regulation parents and up to eight explicit numeric paragraph references accompany extraction and verification. Unresolved/omitted references are disclosed. This is not exhaustive semantic dependency traversal.
- An independent-step/case/action inventory maps to output obligations one-to-one. Local coverage checks run before response caching and inside bounded retries. Mandatory actions and permissions split; shared conditions and OR alternatives remain attached.
- Applicability decisions require product/source evidence. Missing specification detail does not prove absence. Applicable approval, documentation and test duties are not blanket-excluded. Non-normative rationale is not emitted as requirements.
- Removed the final regex applicability filter, fuzzy near-duplicate deletion, hard-coded pulse-table expansion and post-verifier syntactic splitting. Exact text duplicates within the same regulation/paragraph are still removed. Source-grounded extraction and verification handle tables and atomicity.
- Existing stage 0 parsing repairs, stage 1 product reading, stage 2 regulation gating, exhaustive clause ledger, second pass and official output validation remain. Model results and applicability exclusions are retained in the experiment's runs/cache artifacts.

## Run from repository root

```powershell
python -m pip install -r approaches/experiments/leo-certi-atomic-context/requirements.txt
python approaches/experiments/leo-certi-atomic-context/run.py --case heldout-front-bumper
```

Set your own `ANTHROPIC_API_KEY` in the root or experiment `.env`. No shared keys or teammate runs are used. Output: `approaches/experiments/leo-certi-atomic-context/outputs/predictions-heldout-front-bumper.json`. The original approach/output is untouched. All responses are cached locally; rerunning identical inputs resumes via cache. Live logs show approximate Sonnet spend at $2/$10 per million input/output tokens (billing may differ). Full-run cost and runtime have not been measured. No model run or tests were executed during implementation; only Python syntax was inspected.

## Reproducible comparison

Run dev and holdout explicitly, then score saved outputs; neither generation command reads expected answers:

```powershell
python approaches/experiments/leo-certi-atomic-context/run.py --case dev-rear-lamp
python approaches/experiments/leo-certi-atomic-context/run.py --case holdout-acpe
python approaches/benchmarking/bench.py leo-certi-atomic-context approaches/experiments/leo-certi-atomic-context/outputs/predictions.json ../industrial-ai-hackathon/cases/dev-rear-lamp/expected.json --index ../industrial-ai-hackathon/regulations/index.json
python approaches/benchmarking/bench.py leo-certi-atomic-context approaches/experiments/leo-certi-atomic-context/outputs/predictions-holdout-acpe.json approaches/benchmarking/cases/holdout-acpe/expected.json --index ../industrial-ai-hackathon/regulations/index.json
```

Compare all page/clause/regulation P/R/F1/F2 metrics with the already-saved Certi results; do not regenerate the teammate's baseline. Those local metrics are proxies, not platform requirement F2. An optional model-based requirement judge costs additional API credits and must be invoked separately. No held-out bumper gold is available. Avoid tuning on the held-out case. Results history: initial implementation, no scores. Inherited regulation-specific rules and development-driven design give this experiment a high declared overfit risk.
