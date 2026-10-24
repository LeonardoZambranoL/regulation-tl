# devansh-writer-faithful-ranked

Owner: Devansh. **The best pipeline with a writer that keeps the regulation's own scope, subject, values and
alternatives instead of narrowing them to the product.** Why: in paragraphs the experts did list, the local judge left
38 of our requirements and 10 expert requirements unmatched, mostly because the writer narrowed the scope ("M1" for
"M1 and N1"), dropped half of a combined obligation, or named the wrong device. Method: [EXPLAIN.md](EXPLAIN.md);
risk: `risk.json`.

Run (your own Anthropic credits; cached): `bash approaches/experiments/devansh-writer-faithful-ranked/run.sh` from the
repo root. Results: `results.json`, `approaches/req_scores.json`, dashboards, devansh-toolkit/HISTORY.md.

## Results (2026-10-24): adopted, current best for the requirement level

| local requirement judge | requirements | P | R | F1 | F2 |
|---|---|---|---|---|---|
| dev, ranked writer (previous best) | 312 | 0.474 | 0.779 | 0.590 | 0.690 |
| **dev, faithful writer + ranker** | **289** | **0.505** | 0.768 | **0.610** | **0.696** |
| holdout-acpe, previous best | 166 | 0.265 | 0.468 | 0.338 | 0.406 |
| **holdout-acpe, faithful** | **152** | **0.283** | 0.457 | **0.350** | **0.407** |

Clause F2 on dev 0.619 -> 0.708. Upload file: `outputs/predictions.json` (validate first).

## Former final (2026-10-24), superseded by [devansh-profile-faithful](../devansh-profile-faithful/)

This is the team's final pipeline. Clean, validated file for the dev case:
`outputs/submission-dev-rear-lamp.json` (289 requirements, team-11, every requirement with page and paragraph;
`tools/validate.py --strict` OK; local score_local: regulations 1.0, pages P 0.658 / R 0.943).

For the held-out case on Sunday (after `git pull` in ../industrial-ai-hackathon):

```bash
bash approaches/experiments/devansh-writer-faithful-ranked/final.sh <held-out-case-id>
```

It runs the whole pipeline for that case, writes `outputs/submission-<case-id>.json` in the clean submission format and
validates it. Upload that file.
