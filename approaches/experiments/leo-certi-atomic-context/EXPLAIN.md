# In plain words

This variant starts from Certi's pipeline, reads the product and selects relevant regulations. Claude checks the selected clauses and lists separate obligations, with their conditions and citations. It sees complete source text and nearby governing sections instead of cut-off excerpts. A second check removes clearly unsupported or incompatible items, while retaining uncertain conditional duties. Its main risks are selecting the wrong regulations and retaining too many similar or conditional requirements.

# Technical

1. Fork Certi stages 0–6 locally, using shared base clause JSON and regulation index read-only. No expected data enters inference.
2. Run product reader and inherited hybrid gate with Sonnet 5.5; dense retrieval remains disabled by default. Existing ingestion and gate heuristics remain.
3. Extract with batches <=8 clauses / 14,000 source characters and two workers, complete source text, numeric parent context and up to eight explicit references. Context can exceed the batching character bound.
4. Require an explicit source-unit inventory with distinct obligation indexes; validate coverage, statuses, IDs and text lengths before caching. Use existing three-attempt retry boundary with validation feedback.
5. Verify with complete source/context and product evidence, preserving conditions and independent steps. Drop only supported exclusions. Disable blanket final regex filtering, numeric template output and mechanical final splitting. Deduplicate exact normalized-whitespace/case text within a regulation/paragraph only.
6. Validate and write official main-challenge JSON with base-version citations; keep all artifacts/caches local to this variant. Log approximate token cost. No measured dev/holdout scores; high inherited/development-driven overfit risk. No prediction improvement is claimed until evaluated.
