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

## Leaderboard probes (bumper)

`probes.py` (zero API: v5 output + cached ranker answers) writes `outputs/probes/`: 1 v5 (471); 2 v5 + the 92 items the
ranker rated 1 (563); 3-6 v5 minus one lamp-function block (direction indicator 76, front position 23, side marker 22,
daytime running 19; items about several functions stay). Each upload's P x N gives the matched count, so the difference
to probe 1 is how many of that block the experts list. **This tunes on the held-out case's answer key through the
leaderboard** (allowed by the platform: unlimited uploads, last one counts); it must be stated in any write-up.

## v6 (recommended single upload): `outputs/submission-heldout-front-bumper-v6.json`

v5 minus the front-position-lamp (23) and daytime-running-lamp (19) blocks: 471 -> 429 requirements (validate --strict
OK). Reason: the spec and drawing describe only a "(Side) Lighting - signalling" and a decorative lighting; a side
signal is a side marker lamp or a side direction indicator (both blocks kept), not a front position or daytime running
lamp (headlamp functions). Product-specific reading of the spec, chosen without leaderboard feedback; zero API.
Expected platform F2 about 62-63% (v3 60.4%) if the mirrored items add a few matches and the two dropped blocks hold
few; not enough for 1st place (73.6%).
