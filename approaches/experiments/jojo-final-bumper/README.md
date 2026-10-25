# jojo-final-bumper

Upload **`outputs/submission-heldout-front-bumper.json`**: team-11, heldout-front-bumper, 546 requirements, only id/text/source per item. Official strict validation passed. This is a byte-identical copy of Devansh v7's final certi-pipeline-minus-band-1 artifact, not a newly improved model output.

The authenticated platform showed the current 546-item submission at **P 31.9%, R 83.7%, F2 63.1%**, scored 25 October 2026 at 11:18:33 CET: [submission detail](https://hackathon.certivity.io/submissions/df8155d8-c582-43c8-9e91-9d49a5dbb449). That is 0.3 percentage points above the task's 62.8% baseline. Expected performance for this preserved candidate is about 63.1%; no new upload or independent semantic judge was run. The platform did not expose a content hash, so the platform observation is identified by the submission record and 546-item count, not a downloaded byte comparison. The live leader was 77.4%, above the stale 73.6% in the task.

If a future candidate scores worse, re-upload **`outputs/fallback-heldout-front-bumper.json`**, which preserves this same best-known 546-item artifact. Only the last upload counts.

## Method and decision

1. Read the supplied task, current AGENTS.md, CONTRIBUTING.md, certi-pipeline README, v7 code/calibration and history rows 29–51. Fetch current origin/main before editing. Original checkout's pull was blocked by unrelated untracked files; preserve them and work in a separate checkout on `codex/jojo-final-bumper`, starting at d7c94fb.
2. Reuse committed predictions/ratings as explicitly requested; do not regenerate another person's pipeline. Our deterministic postprocessor removes rating 1 from certi's dev/ACPE predictions: 209→206 and 163→163. Preserve all regulations and requirement text.
3. Freeze the known 546-item bumper file without further cuts. Its SHA-256 is `52be4906a0c6a6a5a62d270a6e3cc0311cfac8ec90fbdd4cce136caee1f11dfe`.
4. Run the unchanged shared benchmark through this folder's `bench.py` on both cases; its supported root parameter keeps generated history entirely in this experiment. No shared leaderboard/dashboard files are edited or committed, in accordance with the request to commit only our folder. `benchmark-summary.json` contains full P/R/F1/F2 at all three citation levels and both source comparisons.
5. Measure paragraph multiplicities only inside the benchmark. On common paragraphs, certi emits 199 versus 190 expert items on dev, and 70 versus 85 on ACPE. A universal over-splitting claim is not supported. A fixed cap of 3 would remove 22 dev and 15 ACPE items, but exact semantic losses cannot be inferred from paragraph counts. Do not adopt that cut.

## Scores

| Case | Items | Page F2 | Clause F2 | Regulation F2 | Change vs source |
| --- | ---: | ---: | ---: | ---: | --- |
| dev-rear-lamp | 206 | 99.6241% | 98.3740% | 100% | Citation metrics unchanged |
| holdout-acpe | 163 | 72.7273% | 79.5796% | 83.3333% | Citation metrics unchanged |

These are citation scores, not platform requirement scores. This experiment has no previous run. Inherited certi-pipeline dev performance is highly optimistic because that pipeline was tuned on dev. No newly measured semantic hit rates are claimed. Both cases were recorded, and the shared unseen-case consistency check on this experiment's runs reports up to date.

## Offline probes and platform limits

The task described unlimited uploads; the live platform instead showed **5 uploads per rolling 60 minutes**, all used at inspection. The next slots were 11:38, 11:46 and 12:01 CET. No probe was uploaded: a regression must not consume the only available slot and prevent restoring the best file.

`probes/manifest.json` fixes 11 disjoint blocks before any probe result: GTR9, R26, R42, R127, R10 main/annexes, and common/direction/side-marker/position/other lamp groups across R48/R148. It records IDs and counts; optional JSONs are generated with `build.py --probes`. These are untested diagnostic files, not recommendations. No regulation or administrative block is removed from the final file.

For a base with M matches and N submissions, F2 = 5M/(4E+N). A removal of n items with m matches helps iff m/n < M/(4E+N). With inferred M=174, E=208, N=546, the threshold is 12.627%. Fix that decision rule before probes, account for rounded platform percentages, and score the combined candidate before adopting it. Reserve restoration capacity and restore the best scored file last.

## Reproduce

Use Python 3.12+ with `pip install -r approaches/experiments/jojo-final-bumper/requirements.txt`, from repository root:

```sh
python approaches/experiments/jojo-final-bumper/build.py
python approaches/experiments/jojo-final-bumper/bench.py
python ../industrial-ai-hackathon/tools/validate.py approaches/experiments/jojo-final-bumper/outputs/submission-heldout-front-bumper.json --index ../industrial-ai-hackathon/regulations/index.json --strict
```

`build.py` never reads answer keys; `bench.py` alone reads them for scoring and aggregate measurement. All output requirements are inherited, not copied from answer keys. `hooks/pre-commit` checks strict validation, two-case run consistency, secret-like literals and staged path scope, replacing the shared auto-staging dashboard hook for this explicitly folder-only commit. The normal pre-push hook remains active.

## Budget and limitations

Hard API budget **$0**, requests **0**, input/output tokens **0**, spend **$0**; see `spend.json`. No `.env` or configured provider API key was present in this user's requested repository or process, so no API call was attempted and no teammate credentials were used. The assistant does not provide personal API credits. There are no response usage records because no responses were requested.

The original 561-item bumper file and per-item local judge match caches were not present. Ratings contain IDs and scores only, so the missing 15 texts cannot be reconstructed. The previously measured band-1 calibration rests on only 3 dev removals and zero ACPE removals. No comparative rater, semantic cap validation, fresh req_judge run, or new platform upload was performed; further improvement over the current 63.1% remains unproven. See risk.json and HISTORY.md.
