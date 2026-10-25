# In plain words

Same as v3 (keyword rules plus Claude pick the regulations; Claude studies the product description and drawing, picks
the rules that apply, rewrites each into single obligations, does a final 1-5 check), plus one step that only adds.
Some regulations copy another one almost word for word (a UN Regulation that adopts a global regulation), and the
experts list each obligation under both. When our list has an obligation under only one of the two, Claude finds the
same obligation in the other regulation and adds it with that regulation's wording and paragraph. Main weakness: if
the experts did not list a particular obligation twice, the added copy is one more unmatched item.

# Technical

1. v3 pipeline unchanged (regulations `union_component`, profile, `shall+implicit` candidates minus Table / Figure /
   Appendix, classifier, faithful writer, `refine --mode rank --drop-at-or-below 1 --merge-restatements`), cached answers.
2. NEW `retrieval.mirror --min-shared 5`: `refine.merge_pairs` decisions (cached) give confirmed same-obligation pairs
   across regulations; two regulations are linked when >= 5 are shared. For each linked pair (A, B) and each item of A
   (operative text only) with no confirmed partner in B, one Claude call (`claude-opus-5-5`, effort medium) with all of
   B's operative clauses returns the B clause stating the same obligation (or none) and the requirement in B's wording.
3. Bumper: GTR 9 <-> R127 linked (13 shared); 12 + 11 items asked, 3 + 8 counterparts added (460 -> 471). R48 / R148
   (3 shared) not linked. dev and holdout-acpe: no linked pair, outputs identical to v3 (req F2 0.736 / 0.407).
4. Overfit risk: medium; the idea comes from v4's bumper platform result (see `risk.json`).
