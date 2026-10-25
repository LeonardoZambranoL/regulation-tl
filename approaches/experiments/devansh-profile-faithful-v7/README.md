# devansh-profile-faithful-v7

Owner: Devansh. Last precision attempts for the held-out bumper: remove only items very unlikely to match an expert
requirement, without losing recall. Both methods and their decision rules were fixed before measuring.
Explanation: [EXPLAIN.md](EXPLAIN.md).

Break-even: bumper F2 = 5 x matches / (4 x expected + submitted), so removing a block raises F2 only if fewer than
F2 / 5 (about 12% at v6's 61.1%) of its items match. Hit rates below are read from the local judge's cached matches
of the unpruned dev / holdout-acpe files (no new judge calls).

## Round 1: structural pruning (`prune.py`, zero API): rejected

| test | dev removed / matched | holdout-acpe removed / matched | verdict |
|---|---|---|---|
| A administrative sections (approval, approval marks, modification, CoP, penalties, transitional, communication annexes) | 51 / 30 (**59%**) | 5 / 4 (**80%**) | rejected |
| B within-regulation near-repeat (token Jaccard >= 0.85) | 6 / 1 (17%) | 13 / 1 (8%) | rejected |
| C definitions sections | 0 | 0 | nothing to remove |

The administrative obligations are the most precise pool the pipeline produces: never prune them.

## Round 2: sureness rater with clause context (`rate.py` + `calibrate.py`): band 1 dropped

Claude (claude-opus-5-5, effort medium) rates each item 1-5 as a probability band that the expert list contains a
matching obligation (1 < 10%, 2 10-25%, 3 25-50%, 4 50-75%, 5 > 75%), seeing the spec + profile and the **full text of
the clause the item cites**. Rule (declared before the ratings): drop bands <= c for the largest c whose removed items
match < 12% on both cases.

| band | dev matched / items | holdout-acpe matched / items | bumper v6 items |
|---|---|---|---|
| 1 | 0 / 6 | 0 / 0 | 14 |
| 2 | 11 / 47 (23%) | 2 / 6 (33%) | 82 |
| 3 | 44 / 102 (43%) | 6 / 47 (13%) | 129 |
| 4 | 76 / 138 (55%) | 17 / 91 (19%) | 167 |
| 5 | 30 / 41 (73%) | 20 / 33 (61%) | 37 |

Only c = 1 passes (c = 2 removes 21% / 33% matched items). Result: dev 334 -> 328, req F2 0.736 -> **0.740**
(estimated from cached matches: 161 / 190 expected); holdout-acpe unchanged (177, F2 0.407). The bands are well
ordered (the old ranker's rating 2 still matched 28% / 14%), but only the lowest band is safe to cut.

Bumper: v6 429 -> **415** (`outputs/submission-heldout-front-bumper.json`, validate --strict OK).
**Caution:** 8 of the 14 dropped bumper items are GTR 9 rationale-part paragraphs (20, 97, 113-116; incl. the lower
legform limits 19 deg / 6 mm / 170 g) and 4 are R127 5.2.1 / 5.2.2 child-headform HIC limits: the same kinds of items
whose removal in v4 cost about 10 platform matches. Expected platform F2: 61.7% if none of the 14 match, 61.4% if 1,
60.9% if 2, about 59.7% if 4 (v4's 28% rate). It is a test upload: if it scores below 61.1%, re-upload v6
(`devansh-profile-faithful-v5/outputs/submission-heldout-front-bumper-v6.json`); only the last upload counts.

Cost: 55 Claude calls, about $3.46 (dev $1.08, ACPE $0.61, bumper $1.77; $5 / $25 per M tokens assumed).

## Run

    .venv/Scripts/python.exe approaches/experiments/devansh-profile-faithful-v7/rate.py <submission.json> <spec-with-profile.md> <ratings.json> --budget-usd 3
    python approaches/experiments/devansh-profile-faithful-v7/calibrate.py <ratings-dev.json> <judge-dev.json> <ratings-acpe.json> <judge-acpe.json>

Ratings are cached in `.cache/` (git-ignored); outputs/ratings-*.json hold every item's band.
