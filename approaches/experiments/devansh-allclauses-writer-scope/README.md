# devansh-allclauses-writer-scope

Owner: Devansh. rules pick the regulations, Claude judges every clause (no shall filter), writer splits obligations, scope ranker drops what experts leave out.

Why: on the platform the ranked writer scored requirements P 42.9% / R 70.5% / F2 62.5%. 92 of the 187 paragraphs it
cites (134 of 312 requirements) are paragraphs the experts did not list; 26 expert paragraphs (34 requirements) were
never kept. Method and steps: [EXPLAIN.md](EXPLAIN.md). Risk: `risk.json`.

Run (your own Anthropic credits; cached): `bash approaches/experiments/devansh-writer-ranked-scope/run_scope.sh` from the
repo root runs both scope experiments, scores them and pushes.

Results: `results.json`, `approaches/req_scores.json`, dashboards, devansh-toolkit/HISTORY.md.
