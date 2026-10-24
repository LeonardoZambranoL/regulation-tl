# devansh-deliberate-faithful-ranked

Owner: Devansh. **An agent picks the exact clauses section by section, thinking with the whole section in view; then
the faithful writer and the 1-5 ranker.** Why: we find the right pages (96%) but not the right clauses: 92 of 187 cited
paragraphs were not the experts' and 26 expert paragraphs were missed, because the old filter judged 40 unrelated
clauses at a time without their section. Method: [EXPLAIN.md](EXPLAIN.md); risk: `risk.json`; the agent's reason for
every chosen clause: `outputs/*-clause-reasons.json`.

Run (your own Anthropic credits; cached): `bash approaches/experiments/devansh-deliberate-faithful-ranked/run.sh`.

## Results (2026-10-24): not adopted on its own

Clause selection is more precise (paragraph precision 0.553 vs 0.508) but misses more (recall 0.736 vs 0.785).
Local req F2: dev 0.635 (P 0.492, R 0.684), holdout 0.337, vs best 0.696 / 0.407. Where it agrees with the classifier,
paragraphs are 80% right on dev; see devansh-agreement-combo.
