# devansh-profile-faithful

Owner: Devansh. **The faithful pipeline, plus (1) a product profile Claude builds from the spec and the exploded-view
image, used by every step, and (2) candidates that include obligations written without "shall".** Aimed at more true
positives: the faithful pipeline never considers 23 of the 121 expert paragraphs and decides applicability from the
raw spec text alone. Method: [EXPLAIN.md](EXPLAIN.md); risk: `risk.json`.

Run (your own Anthropic credits; cached): `bash approaches/experiments/devansh-profile-faithful/run.sh` from the repo root.

## Results (2026-10-25): adopted, new FINAL

| local requirement judge | requirements | true positives | P | R | F1 | F2 |
|---|---|---|---|---|---|---|
| dev, faithful (previous final) | 289 | 146 | 0.505 | 0.768 | 0.610 | 0.696 |
| **dev, profile + implicit** | 359 | **164** | 0.457 | **0.863** | 0.597 | **0.733** |
| holdout-acpe, faithful | 152 | 43 | 0.283 | 0.457 | 0.350 | 0.407 |
| **holdout-acpe, profile + implicit** | 235 | **50** | 0.213 | **0.532** | 0.304 | **0.409** |

More true positives and higher F2 on both cases; slightly lower precision / F1. Regulation selection uses the original
spec (the profile's wording triggered extra regulations when it was used there).

Upload: `outputs/submission-dev-rear-lamp.json` (359 requirements, team-11, validate --strict OK; local score_local:
regulations 1.0, pages P 0.595 / R 0.943). Held-out case: `bash approaches/experiments/devansh-profile-faithful/final.sh <case-id>`.

## Platform score (uploaded 2026-10-25 00:29 CEST, dev rear lamp): confirmed best

Requirements P 43.5% / R 82.1% / F1 56.8% / **F2 69.7%**; pages P 59.5% / R 94.3%; regulations 100%.
Faithful writer uploaded right after: P 47.8% / R 72.6% / F1 57.6% / F2 65.8%. The local judge reads about 3.7 points
high on both files (0.733 vs 69.7%, 0.696 vs 65.8%), so it ranks versions correctly.
