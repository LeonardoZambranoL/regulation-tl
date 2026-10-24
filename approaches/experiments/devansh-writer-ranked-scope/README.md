# devansh-writer-ranked-scope

Owner: Devansh. best writer output (ranked), then a scope ranker drops what experts leave out: conditional variants for features the spec does not state, conformity-of-production and approval-process rules, pure cross-references, lab-procedure steps without a result, and functions of the vehicle rather than the product.

Why: on the platform the ranked writer scored requirements P 42.9% / R 70.5% / F2 62.5%. 92 of the 187 paragraphs it
cites (134 of 312 requirements) are paragraphs the experts did not list; 26 expert paragraphs (34 requirements) were
never kept. Method and steps: [EXPLAIN.md](EXPLAIN.md). Risk: `risk.json`.

Run (your own Anthropic credits; cached): `bash approaches/experiments/devansh-writer-ranked-scope/run_scope.sh` from the
repo root runs both scope experiments, scores them and pushes.

**Verdict (2026-10-24): not adopted.** Local requirement F2 below the ranked writer on both cases (it removed too many real matches).

Results: `results.json`, `approaches/req_scores.json`, dashboards, devansh-toolkit/HISTORY.md.
