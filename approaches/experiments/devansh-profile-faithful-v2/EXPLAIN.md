# In plain words

The same steps as our best version (Claude studies the product description and drawing, picks the rules that apply,
rewrites each rule into single obligations, and does a final 1-5 check), with two clean-ups aimed at fewer wrong
answers. First, it no longer turns value tables, figures and appendices into requirements: in the regulations, a
numbered paragraph says "the lamp shall meet the values in Table 7", and the experts list that paragraph, not every
cell of the table. Second, at the end Claude looks for obligations that appear twice in the list (for example a limit
stated in the main text and again in an annex) and keeps only one copy, because each expert requirement can be matched
only once. Every answer is generated fresh for this version; nothing is reused from earlier runs. Main weakness: if
experts for a future product do cite a table, those requirements are now missing.

# Technical

1. Fresh LLM cache: `LLM_CACHE_DIR=approaches/experiments/devansh-profile-faithful-v2/.cache` (git-ignored); all
   Claude answers (profile, classifier, writer, ranker, restatement merge) are generated for this run only.
2. `profile.build_profile` (`claude-opus-5-5`, effort high) from spec.md + exploded-view image, appended to the spec.
3. Regulation selection `combined` (keyword rules + supersession + category filters) on the ORIGINAL spec.
4. Candidates `shall+implicit` (shall / must clauses + implicit-obligation patterns), NEW: minus clauses whose cited
   paragraph label starts with `Table`, `Figure` or `Appendix` (`filter.exclude_labels`; dev 1,599 -> 1,517 candidates).
   Annex paragraphs are kept.
5. Clause classifier (opus 5.5, effort medium) with the profile-augmented spec; faithful writer (effort medium).
6. `refine --mode rank --drop-at-or-below 1` (exact / near-text dedupe, drop only rating 1, cut-off inherited).
7. NEW `refine --merge-restatements`: per regulation (batches of up to 150 items, page order), Claude returns groups of
   items that state exactly the same obligation (same subject, condition, value); conservative rules exclude different
   values / categories / voltage systems, pointer vs detailed test text, and halves of one clause. From each group the
   copy at a numbered main-text paragraph (else the earliest page) is kept.
8. Scored once with `bench.py` and `req_judge.py` on dev-rear-lamp and holdout-acpe; see README for P / R / F1 / F2.
   Overfit risk: medium (step 4 comes from a dev error analysis; see `risk.json`).
