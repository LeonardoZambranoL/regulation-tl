# devansh-profile-faithful-v4 (not adopted: bumper platform F2 58.1% < v3 60.4%)

Owner: Devansh. **v3 plus three generic removal steps after the ranker (rationale part, duplicate obligations, items
about things the product lacks) and a regulation override.** Aim: precision on the front bumper (v3 platform: P 33.9% /
R 75.0% / F2 60.4%, regulations 100%) without losing recall. Method: [EXPLAIN.md](EXPLAIN.md); risk: `risk.json`.

Run: `bash approaches/experiments/devansh-profile-faithful-v4/run.sh` (dev + holdout-acpe, scored).
Bumper: `REGULATIONS="UN GTR 9,UN R10,UN R26,UN R42,UN R48,UN R127,UN R148" bash approaches/experiments/devansh-profile-faithful-v4/final.sh heldout-front-bumper`.

## Platform score (uploaded 2026-10-25 09:48 CET, bumper): WORSE than v3, not adopted

Requirements P 34.4% / R 70.2% / F1 46.2% / F2 **58.1%** (v3: P 33.9 / R 75.0 / F2 60.4); pages P 52.7 / R 92.5 (v3 51.0 /
94.3); regulations 100%. About 146 matches vs 156: **10 of the 36 removed items were correct.** Exactly one expert page
was lost; the 5 pages only v3 cites are GTR 9 pp. 4, 15, 17, 18 (rationale skip) and R127 p. 36 (pair merge). Most
likely cause: the experts list the same obligation under both GTR 9 and R127, so merging cross-regulation duplicates
deletes matches (the dev observation, one copy for R48 / R148 lamp colours, did not carry over). Lesson: on a new
product, removal steps that dev cannot test cost recall; v3's bumper file (60.4%) stays the final held-out upload.

## What each change does (ablation on v3's output, local requirement judge)

| change | dev P / R / F1 / F2 | ACPE P / R / F1 / F2 | bumper items | verdict |
|---|---|---|---|---|
| v3 (base) | 0.482 / 0.847 / 0.615 / 0.736 | 0.254 / 0.479 / 0.332 / 0.407 | 460 | |
| regulation override (forced 7) | no change | no change | 460 (R13H gave none) | used for the bumper |
| skip rationale part | identical (no such part) | identical | -14 (GTR 9) | adopted |
| merge duplicate pairs | **0.488 / 0.853 / 0.621 / 0.742** | identical | -16 | adopted |
| subject check | identical (0 "absent") | identical (0 "absent") | -10 | adopted |
| marking re-split | 0.463 / 0.847 / 0.599 / 0.727 | 0.249 / 0.468 / 0.325 / 0.398 | +11 | rejected |
| **v4 = override + rationale + pairs + subject** | **0.488 / 0.853 / 0.621 / 0.742** | 0.254 / 0.479 / 0.332 / 0.407 | **424** | |

Not built, decided up front: procedure-step removal (the experts list test-method obligations such as "shall be tested
by the method of Annex 9"); borderline re-asking of the classifier (it gives no confidence, and earlier auditor / voting
runs lost true positives); a profile that commits to one lamp function (the bumper's drawing only says "(Side)
Lighting (signalling)", so choosing would be a guess that could remove a whole block of correct items).

## Bumper: what v4 removes (no answer key)

| regulation | v3 | v4 | change |
|---|---|---|---|
| UN R48 | 171 | 165 | -6 |
| UN R148 | 126 | 126 | 0 |
| UN R10 | 62 | 62 | 0 |
| UN GTR 9 | 39 | 17 | -22 |
| UN R26 | 26 | 26 | 0 |
| UN R127 | 24 | 16 | -8 |
| UN R42 | 12 | 12 | 0 |
| total | 460 | 424 | -36 |

- Rationale part (14, GTR 9 paras 20, 97, 113, 115, 116 on pages 4-18): e.g. "In the lower legform to bumper test,
  the maximum lateral knee bending angle shall be <= 19.0 deg" (an old value from the explanatory part).
- Duplicate pairs (16): 13 GTR 9 <-> R127 pairs (e.g. GTR 9 5.1.1 legform limits kept as R127 5.1.1), 3 R48 5.15
  lamp colours kept as the R148 versions.
- Subject check (10): R127 5.2.1 / 5.2.2 headform HIC limits (bonnet-area tests, 7 items) and R48 5.15 colours of the
  end-outline marker, exterior courtesy and manoeuvring lamps.

Expected effect on the bumper's platform score: if all 36 were unmatched, P 33.9% -> about 36.8% at R 75.0%, F2 60.4%
-> about 62.1%. Risk: R127 transposes GTR 9 into UN law; if the experts listed both copies of the 13 legform
obligations, those were matches, giving about P 33.7% / R 68.8% / F2 57%. On dev the experts listed only one copy of
cross-regulation duplicates (R148's lamp colours, not R48's), which is why the pair merge is in.

Upload candidate: `outputs/submission-heldout-front-bumper.json` (424 requirements, team-11, validate --strict OK).

## Limitations

- The changes were chosen after reading v3's bumper output (no answer key); dev / ACPE are guards, not proof.
- The judge's matching is itself an LLM: the dev gain (+1 match, -2 items) is small.
- Shares v2's LLM cache: unchanged prompts reuse earlier answers; new steps (pairs, subject check, marking pass) are fresh.
- `outputs/ablation/` holds every variant file used in the table above.
