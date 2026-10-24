# In plain words

Claude reads the product specification and chooses several searches for relevant rules. Each search finds similar clauses in our local database. We keep every regulation found by any search and give all its clauses to workers to check against the product. A second model checks the proposed requirements, and the script exports supported matches. A regulation missed by every search will not be assessed, and uncertain matches can still be missed.

# Technical

1. Read the shared LanceDB `clauses` table (26,769 records, 56 regulation/version groups in the current corpus). Validate base versions against the challenge index; never read answer keys.
2. `claude-sonnet-5-5` chooses adaptive native tool searches: at least 4 distinct queries, at most 12 tool calls over 8 rounds per planning attempt. Embed plain query text using the same shared REST helper as clause ingestion, with `gemini-embedding-2-preview` and 768 dimensions. Validate the shared database model manifest first; no embedding-model fallback.
3. For every query, run exact cosine comparison against all 26,769 clauses and group results into distinct regulation/version candidates. Rank each regulation by the average of its 3 strongest clause similarities, keep the top 25 regulations per query, then union candidates across queries. Save the supporting clause traces and give the planner compact representative snippets.
4. Scan all clauses in selected groups. `claude-sonnet-5-5`, 10 workers, at most 12 clauses/14,000 characters per batch, 24,000 context characters. Oversized individual clauses are intact. Workers have lexical search/read context tools, up to 4 rounds/8 calls, and may emit only their assigned clauses. Retry failed batches twice.
5. Independently verify proposed requirements using `claude-sonnet-5-5` and the same context tools. Only supported candidates enter predictions; no requirement deduplication. Uncertain/irrelevant assessments are not independently reassessed.
6. Validate the official output schema. Save separate predictions, diagnostics, retrieval trace, Claude cost estimate, and unpriced Gemini request counts. Output size depends on supported candidates and must meet official limits. Spec text only; no product image.
7. No paid full run or dev/holdout scores yet. No dev tuning; medium risk from agent retrieval omissions and verification filtering. Full selected-regulation coverage is not proof of exhaustive regulation coverage. The original embedding archive does not record document prompt formatting.
