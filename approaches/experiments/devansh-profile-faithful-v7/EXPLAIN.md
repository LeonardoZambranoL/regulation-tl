# In plain words

This takes the best earlier requirement list and tries to remove only the items that are almost surely wrong. First
it tried simple rules (paperwork sections, near-copies, definitions): on the two cases with an answer key those items
were right too often, so the rules were dropped. Then Claude read each item next to the regulation text it came from
and the product description, and gave it a 1-5 score for how likely the experts list it. Only the lowest score was
right rarely enough (0 of 6) to remove, so 6 items go on the test case and 14 on the bumper. Then it tried adding our items to Anjaney's better list (certi-pipeline): almost none of ours were new correct
answers, so instead the same 1-5 scoring was run on his list and his 15 lowest-scored bumper items were removed
(546 left). Weakness: the lowest group is tiny on the test cases, so the gain is at most about 0.7 points.

# Technical

1. Input: devansh-profile-faithful-v3 predictions (dev 334, holdout-acpe 177; devansh-profile-faithful-v4/outputs/
   ablation/*-base.json) and the bumper v6 file (429).
2. Round 1 (prune.py, zero API): structural tests A administrative sections, B token Jaccard >= 0.85 within a
   regulation, C definitions. Removed-item hit rates (cached req_judge matches): A 59% / 80%, B 17% / 8%, C none.
   Rejected (rule: < 12% on both cases).
3. Round 2 (rate.py): claude-opus-5-5, effort medium, batches of <= 20 items of one regulation; context = spec +
   profile, regulation title, full cited clause text (team-parsed clauses, <= 2500 chars). Output: probability band 1-5.
4. calibrate.py: largest cut-off c with removed hit rate < 12% on dev and holdout-acpe. Result c = 1
   (dev 0/6, ACPE 0/0; c = 2 would be 21% / 33%).
5. Output: dev 328 (req F2 0.736 -> 0.740, estimated from cached matches), ACPE 177 (0.407), bumper 415.
   Overfit risk medium: cut-off rule fixed in advance; band 1 is calibrated on only 6 dev items. Cost about $3.5.
6. Round 3 (combine.py): certi-pipeline file + our items at paragraphs it does not cite; added items matched 2/146 dev,
   0/54 ACPE (union judged once): rejected.
7. Round 4: rate.py on certi-pipeline's dev (209), ACPE (163) and bumper (561) items; band 1 = 0/3 dev, 0/0 ACPE,
   band 2 = 80% / 25% matched. Drop band 1: FINAL bumper file 546 (his 561 minus 15). Total cost about $7.1.
