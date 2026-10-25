# devansh-profile-faithful-v7 (negative result: nothing adopted)

Owner: Devansh. Last precision attempt for the held-out bumper: remove items that structurally **cannot** be a
distinct expert obligation, without losing recall. Method and rule were fixed before measuring
(`prune.py`, zero API calls). Explanation: [EXPLAIN.md](EXPLAIN.md).

## Break-even

Bumper F2 = 5 x matches / (4 x expected + submitted). Removing a block raises F2 only if fewer than F2 / 5 (about
12% at v6's 61.1%) of its items match.

## Tests (pre-declared) and the measured hit rate of what each would remove

Hit rate = removed items the local judge matched in the base file / removed items (cached answers, no API).

| test | dev-rear-lamp removed / matched | holdout-acpe removed / matched | bumper v6 would remove | verdict |
|---|---|---|---|---|
| A administrative sections (approval, approval marks, modification, conformity of production, penalties, transitional, communication / information-document annexes) | 51 / 30 (**59%**) | 5 / 4 (**80%**) | 43 | rejected |
| B within-regulation near-repeat (token Jaccard >= 0.85) | 6 / 1 (17%) | 13 / 1 (8%) | 9 | rejected (dev above 12%) |
| C definitions sections | 0 | 0 | 0 | nothing to remove |

No component meets "below 12% on both cases", so v7's outputs equal v3's (dev P 0.482 / R 0.847 / F2 0.736;
holdout-acpe P 0.254 / R 0.479 / F2 0.407).

## Findings

- Administrative obligations (approval marks, marking, conformity of production) are the **most** precise pool the
  pipeline produces (59-80% matched): the experts list them. Never prune them.
- Exact / near repeats inside one regulation still match sometimes (the experts restate a value in several places).
- With the 7 regulations fixed and every earlier filter (GTR 9 rationale skip, cross-regulation merge, subject check,
  ranker rating, R48 lamp blocks) costing correct items, no zero-cost pruning is left that beats the break-even.

## Bumper upload

Keep **`devansh-profile-faithful-v5/outputs/submission-heldout-front-bumper-v6.json`** (429; platform F2 61.1%).
v7 writes no new bumper file. `outputs/prune-report-heldout-front-bumper.json` lists the bumper items each test flags.

## Run

    python approaches/experiments/devansh-profile-faithful-v7/prune.py <in.json> <out.json> --tests "" --report r.json

`--tests AB` would apply components A and B (not recommended, see above).
