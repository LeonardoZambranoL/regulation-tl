# In plain words
The method reads a product specification and checks each supplied regulation clause.
Claude Haiku decides whether each assigned clause applies and can look up other clauses for context.
Claude Sonnet independently checks proposed requirements before they are included.
The output contains requirements with citations, plus separate diagnostic and cost reports.
Its main weaknesses are incorrect applicability decisions, uncertain source text, and unresolved or failed batches.

# Technical
1. Read all 26,769 records from the base-regulation clause JSONs; never read expected.json during generation.
2. Partition consecutive records into batches of up to 12 / 14,000 characters, with up to 24,000 characters of initial context; use 10 concurrent workers.
3. Assess with claude-haiku-5-5 and verify with claude-sonnet-5-5. Each agent may use native search/read tools for up to 4 rounds / 8 calls. Retry failed batches twice.
4. Require evidence and restrict proposals to their assigned clauses; retain supported requirements without deduplication. No embeddings or database are used.
5. Export schema-compatible requirements; this saved run covers 26,709 of 26,769 records, with 1,058 assessments still needing context.
6. Rebenchmark on 2026-10-24: page F2 0.543478, clause F2 0.287081, regulation F2 0.800000. Page/regulation scores are unchanged; clause F2 is newly reported by the updated evaluator.
7. Overfit risk: medium; only the rear-lamp dev case has been evaluated. Parsing and examples were checked against dev inputs; no gold data is used by the generation pipeline.
