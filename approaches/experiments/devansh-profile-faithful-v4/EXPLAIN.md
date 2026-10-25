# In plain words

Same as v3 (keyword rules plus Claude pick the regulations; Claude studies the product description and drawing,
picks the rules that apply, rewrites each into single obligations, does a final 1-5 check, skips value tables), plus
three clean-ups at the very end that only remove items. (1) Some regulations open with a long explanation of why they
were written, with old values; v4 drops anything cited from that part. (2) When two regulations (or a clause and its
sub-clause) state the same obligation, Claude confirms it and v4 keeps one copy, because each expert requirement can be
matched only once. (3) Claude says what each requirement is about ("the courtesy lamp", "the bonnet headform test")
and whether the product has it; items about things the product clearly lacks are removed. When the regulations are
known, they can be given directly. Main weakness: if the experts did list both copies of an obligation stated in two
regulations, the duplicate removal loses those matches; and a vague description (which signal the corner lamp is)
still keeps the rules for every possible meaning.

# Technical

1. Regulations: `union_component` (keyword rules + Claude's product-level picks), as v3. NEW override:
   `export --regulations "A,B,..."` (or config `regulations`): requirements are cited only from these; candidates are
   the automatic picks plus any listed regulation they lack, so the classifier batches (and cached answers) stay the same
   when the picks already cover the list. Bumper final: GTR 9, R10, R26, R42, R48, R127, R148.
2. Profile, `shall+implicit` candidates minus Table / Figure / Appendix labels, classifier, faithful writer,
   `refine --mode rank --drop-at-or-below 1 --merge-restatements`: as v2 / v3 (cached answers reused).
3. NEW `--skip-rationale`: drop items cited before a regulation's "II. Text of the Regulation" heading (GTR layout;
   in the corpus only UN GTR 9, operative text from page 56).
4. NEW `--merge-pairs`: candidate pairs = items of different regulations with word-set Jaccard >= 0.5, and items at a
   parent paragraph + one of its sub-paragraphs; Claude (`claude-opus-5-5`, effort medium, 40 pairs per call) answers
   same / general / different and which copy to keep (the regulation approving the product itself, else the more
   specific wording); only the redundant member is dropped.
5. NEW `--subject-check`: Claude names each item's subject and answers has / possible / absent from the
   profile-augmented spec; only "absent" is dropped (optional, conditional or unknown = possible).
6. All v4 steps run AFTER the ranker on v3's cached output, so each removes only what it targets.
7. Tested and rejected: marking re-split (one requirement per marking and per object), dev +14 items with no new match
   (F2 0.736 -> 0.727) and ACPE -1 match (0.407 -> 0.398). Not built: procedure-step removal (the experts list test-method
   obligations), borderline re-asking (earlier voting / auditor runs lost true positives).
8. Scores (local requirement judge): dev P 0.488 / R 0.853 / F2 0.742 (v3 0.482 / 0.847 / 0.736); ACPE unchanged
   0.254 / 0.479 / 0.407. Bumper: 460 -> 424 requirements. Overfit risk: medium (`risk.json`).
