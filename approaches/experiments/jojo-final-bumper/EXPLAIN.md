# In plain words

We preserve the team's latest 546-item bumper submission and package it as a validated upload file. For the two practice cases, we apply the already tested rule that removes only the lowest-rated items. We check the files and measure which pages, paragraphs and regulations they cover. We also prepare groups for possible future platform tests, but do not remove any new group without evidence. The limitation is that no new paid model checks or platform uploads were available, so this preserves the existing result rather than proving a further gain.

# Technical

1. Start from origin/main d7c94fb. Inputs: committed certi-pipeline dev/ACPE predictions, v7 ratings-certi-*.json, and v7 final bumper JSON. Source ratings were made by claude-opus-5-5 at medium effort; no model or API runs in this experiment. The requested Codex Astra/high execution does the analysis and packaging, not paid regeneration.
2. Deterministic rule: retain saved rating >1 on dev/ACPE, producing 206/163 requirements; keep bumper's existing 546 exactly, including order, IDs, citations and text. All seven bumper regulations remain.
3. Validate against the official index with --strict; final and fallback share SHA-256 52be4906a0c6a6a5a62d270a6e3cc0311cfac8ec90fbdd4cce136caee1f11dfe.
4. Shared benchmark, unchanged scoring code, isolated output root: dev page/clause/regulation F2=0.996241/0.983740/1.0; ACPE=0.727273/0.795796/0.833333. All equal their source citation metrics. No fresh requirement-level judge score exists.
5. Aggregate over-splitting diagnostic: common-paragraph submitted/expert items=199/190 dev and 70/85 ACPE. A cap of 3 is measured but not applied; no <12% semantic-loss evidence supports it on both cases.
6. Eleven optional leave-one-block-out probes are fixed before scoring. Adopt a removal only if removed-match fraction <174/1378, then re-score its combined candidate. No probe scores or new platform upload are claimed. Platform quota is five per rolling hour; preserve restoration capacity.
7. High overfit risk: inherited dev-tuned pipeline, rating calibration using labelled cases, and known target platform score; no answer-key text/citations enter generation. Expected bumper F2 is about 63.1% based on the live current 546-item submission, versus the requested 62.8% baseline. No further gain is established. API budget/spend is $0.
