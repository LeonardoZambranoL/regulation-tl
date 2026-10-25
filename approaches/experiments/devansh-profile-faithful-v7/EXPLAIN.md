# In plain words

This is the last attempt to make the bumper submission more precise without losing correct answers. It takes the
best earlier list of requirements and checks three kinds of items that looked like they could never be on the
experts' list: paperwork rules (approval marks, production checks), near-copies of another item in the same
regulation, and definitions. Before applying anything, it checked on the two cases with an answer key how many of
those items the experts actually listed. Too many were right (the paperwork rules were right more often than
anything else), so nothing is removed and the earlier bumper file (v6, 61.1%) stays the one to upload.

# Technical

1. Input: devansh-profile-faithful-v3 predictions (dev 334, holdout-acpe 177; files in
   devansh-profile-faithful-v4/outputs/ablation/*-base.json) and the bumper v6 file (429).
2. Section of each item: the heading clause (team-parsed clauses, data-ingestion/clauses) of the item's top-level
   paragraph number or annex at or before its page.
3. Tests, written down before measuring: A administrative section titles (regex in prune.py), B token Jaccard >= 0.85
   with an earlier item of the same regulation, C "Definitions" sections.
4. Validation: hit rate of each test's removed items from the local requirement judge's cached matches
   (approaches/benchmarking/req_judge.py, claude-opus-5-5, medium; zero new calls). Adoption rule: < 12% (bumper F2 / 5)
   on both cases.
5. Measured: A 30/51 dev, 4/5 ACPE; B 1/6 dev, 1/13 ACPE; C none. Nothing adopted; outputs = v3 (dev req F2 0.736,
   ACPE 0.407). Overfit risk: medium (inherited); no parameter tuned. API cost 0.
