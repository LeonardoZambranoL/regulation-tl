# devansh-profile-faithful-v5

Owner: Devansh. **v3 plus one adding step: obligations mirrored between two regulations that restate each other.**
Method: [EXPLAIN.md](EXPLAIN.md); risk: `risk.json`.

Bumper: `bash approaches/experiments/devansh-profile-faithful-v5/final.sh heldout-front-bumper`.

## Why

Bumper platform scores: v3 F2 60.4% (P 33.9 / R 75.0, 460 items); v4, which removed one copy of 13 obligations that
both GTR 9 and R127 state, F2 58.1% (R 70.2): about 10 matches lost, so the experts list such obligations under BOTH
regulations. v5 does the reverse of v4's merge: it adds the missing copy.

## Result

| case | items | local req judge P / R / F1 / F2 |
|---|---|---|
| dev-rear-lamp | 334 | 0.482 / 0.847 / 0.615 / 0.736 (identical to v3: no linked regulations) |
| holdout-acpe | 177 | 0.254 / 0.479 / 0.332 / 0.407 (identical to v3) |
| heldout-front-bumper | **471** | no answer key |

Bumper additions (11): R127 5.1.1 / 5.1.2 legform limits and Annex 3 3.2 (from GTR 9 items), GTR 9 4.1, 5.2.3 headform
HIC limits (5) and 7.1.1.2 / 7.1.1.3 legform test conditions (from R127 items).

Expected platform F2 vs v3's 60.4%: about 62.6% if 7 of the 11 match, 61.0% if 3 match, 59.8% if none.

Upload files:
1. `outputs/submission-heldout-front-bumper.json` (471, main shot; validate --strict OK).
2. `outputs/submission-heldout-front-bumper-no-rationale.json` (457 = file 1 without the 14 GTR 9 rationale-part items,
   pp. 4-18; validate --strict OK). Try only if file 1 beats 60.4%.

If a file scores below 60.4%, re-upload `devansh-profile-faithful-v3/outputs/submission-heldout-front-bumper.json`:
only the last valid held-out upload counts.

Cost: 2 Claude calls (about 23k tokens of clause text each); everything else came from the cache.
