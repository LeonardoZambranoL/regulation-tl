# devansh-profile-faithful-v3

Owner: Devansh. **devansh-profile-faithful-v2 (platform F2 72.7% on dev) with a better first step: regulations from the
keyword rules PLUS Claude's picks of regulations about the product itself.** Method: [EXPLAIN.md](EXPLAIN.md); risk:
`risk.json`.

Run: `bash approaches/experiments/devansh-profile-faithful-v3/run.sh` (dev + holdout-acpe, scored).
Any case: `bash approaches/experiments/devansh-profile-faithful-v3/final.sh <case-id>`.

## Why

v2 on the held-out front bumper (platform, 2026-10-25): requirements P 24.0% / R 42.8% / F2 37.0%; regulations
P 100% / R 71.4%. Every regulation cited was right but 2 of the 7 expected were never picked, which caps recall for
every downstream step. The keyword rules were written on the rear-lamp case. (That upload was the 371-requirement raw
file, not v2's 301-requirement submission.)

## Regulation picks

| case | keyword rules (v2) | Claude, unrestricted | **v3 = rules + Claude (product itself only)** |
|---|---|---|---|
| dev-rear-lamp | R10, R148, R150, R48 | same | same |
| holdout-acpe | R10, R175 | + R155, R156 | same as v2 |
| heldout-front-bumper | GTR 9, R10, R127, R13H, R42, R48 | + R26, R148, R152, R94, R100, R137, R155, R156, R161 | **+ R26, R148** |

The unrestricted picks add whole-vehicle approvals (crash tests, cyber security, software updates, EV safety,
anti-theft), and on ACPE those are not in the answer key. The instruction "only regulations on the product itself"
keeps the component ones (external projections, the integrated lamps) and adds nothing on dev or ACPE.

## Results

| case | requirements | P | R | F1 | F2 (local judge) |
|---|---|---|---|---|---|
| dev-rear-lamp | 334 | 0.482 | 0.847 | 0.615 | 0.736 (= v2; same regulations, same cached answers) |
| holdout-acpe | 177 | 0.254 | 0.479 | 0.332 | 0.407 (= v2) |
| heldout-front-bumper | 460 | no answer key | | | |

Bumper submission: **`outputs/submission-heldout-front-bumper.json`** (460 requirements, team-11, validate --strict OK).
By regulation: R48 171, R148 126, R10 62, GTR 9 39, R26 26, R127 24, R42 12 (R13H kept none). Compared with v2's 301:
+126 from R148 and +26 from R26. If those regulations are among the expected 7, recall should rise clearly; precision
may fall, since R148 brings many lamp-performance requirements.

## Limitations

- The selection change was prompted by the bumper's platform regulation recall (no answer key was seen); only the
  platform can score it.
- dev and ACPE cannot show any gain: v3 equals v2 there by construction.
- Shares v2's LLM cache: identical prompts reuse v2's answers (that is what makes dev / ACPE identical to v2).
- The restatement merge now breaks ties between same-page copies by list order (previously set order; it changed one
  ACPE item between otherwise identical runs).
