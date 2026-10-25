# In plain words

Same as v2 (Claude studies the product description and drawing, picks the rules that apply, rewrites each rule into
single obligations, does a final 1-5 check, and skips value tables), with one change in the very first step: choosing
which regulations apply. v2 used keyword rules only; on the front-bumper case they missed 2 of the 7 regulations the
experts expected. v3 also asks Claude to pick from the full regulation list, but only regulations about the product
itself (its approval, construction, markings, installation), not approvals of the whole vehicle such as crash tests or
cyber security. Its picks are added to the keyword picks. Main weakness: Claude can still pick a regulation the experts
did not expect, which adds many unmatched requirements.

# Technical

1. Regulation selection `union_component`: `select_rules` (keyword rules) UNION `select_llm` with the extra
   `COMPONENT_SCOPE` instruction (`claude-opus-5-5`, structured output over the 56-regulation catalogue with titles and
   scopes), then the usual supersession and vehicle-category filters, on the ORIGINAL spec.
   Picks: dev = R10, R148, R150, R48 (same as v2); holdout-acpe = R10, R175 (same as v2); heldout-front-bumper = v2's
   GTR 9, R10, R127, R13H, R42, R48 plus R26 and R148. Without the instruction Claude also added R155 / R156 on ACPE
   and R94, R100, R137, R152, R155, R156, R161 on the bumper.
2. Everything else exactly as devansh-profile-faithful-v2 (profile, `shall+implicit` candidates minus Table / Figure /
   Appendix labels, classifier, faithful writer, `refine --mode rank --drop-at-or-below 1 --merge-restatements`).
3. LLM cache shared with v2 (`LLM_CACHE_DIR=devansh-profile-faithful-v2/.cache`): identical prompts reuse v2's answers,
   so dev and holdout-acpe outputs equal v2's; new prompts (regulation picks, the bumper's new batches) are fresh.
4. Overfit risk: medium (see `risk.json`; the selection change was prompted by the bumper's regulation recall).
