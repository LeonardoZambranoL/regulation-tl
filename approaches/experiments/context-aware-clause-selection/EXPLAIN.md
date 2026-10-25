# In plain words

The experiment keeps the current best regulation picker, requirement writer, and gentle final ranker. Its new step
shows each possible rule together with its headings, scope, useful definitions, nearby text, and resolved references,
then asks whether the rule applies, is conditional, is uncertain, or clearly does not apply. Conditional and uncertain
rules stay unless they contain no obligation. A second branch scans all clauses in the same regulations for numerical,
table, prohibition, acceptance, and cross-reference forms that can impose obligations without using “shall” or “must”.
Its main weakness is that parsed paragraph structure is imperfect and unresolved references remain explicitly unknown.

# Technical

1. Regulation selection is unchanged: `retrieval.regselect.select(method="combined")`; selected regulation/version
   pairs are recorded per case.
2. Product model: `claude-sonnet-5-5`, effort medium, structured evidence-bearing facts with explicit unknowns. Image
   captions/alt text are usable; unavailable pixels are not claimed as evidence.
3. Variant A copies the frozen `devansh-llm-clause-filter-writer-ranked` submission. Variant B contextualizes the exact
   existing `shall|must` candidate set. Variant C adds an exhaustive, non-top-k scan for generic normative,
   quantitative, table, acceptance, prohibition, and reference patterns.
4. Context contains the exact clause and provenance, up to three ancestors, scope paragraphs, term-overlapping
   definitions, applicable sibling exceptions/conditions, one neighbor each side, and up to eight resolved references. Optional context is dropped at
   12,000 serialized characters, but the exact target text is never truncated; unresolved labels are logged.
5. Context classifier: `claude-sonnet-5-5`, effort medium, batches of six. It returns applicability, exact evidence,
   conditions, references, and `contains_obligations`. APPLICABLE, CONDITIONAL, and UNCERTAIN obligations are retained.
6. Writer is unchanged: shared `retrieval.write.write`, strict prompt, `claude-sonnet-5-5`, effort medium. Ranker is
   unchanged: shared `retrieval.refine.refine_ranked`, `claude-sonnet-5-5`, effort medium, dedupe and fixed cutoff 1. No gold is read before predictions and
   their traces are hashed in `frozen-manifest.json`.
7. Post-freeze evaluation invokes the official validator, `bench.py`, and `req_judge.py`. Diagnostics attribute every
   unmatched gold/output item from recorded stages and compare gained/lost one-to-one matches. No results exist until
   an authorized owner runs the experiment with their own key.
8. Live `tqdm` bars show batch completion, cache hits, and cumulative estimated API cost. Cost files use returned token
   usage and the public standard-mode Sonnet 5.5 rates pinned with their source and verification date in `config.json`.
