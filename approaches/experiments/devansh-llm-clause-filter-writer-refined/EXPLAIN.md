# In plain words

This is the current best approach plus a final check. First the checklist picks the rulebooks, Claude keeps the
rules that apply, and a writer turns each rule into single, clearly worded obligations. Then a second Claude reviewer
reads the finished list like an engineer would before handing it to a supplier: it removes items that are not real
obligations for this product (definitions, steps of a lab test procedure, paperwork done by the authorities, features
the product does not have) and removes repeats. The scoring robot pairs each of our requirements with at most one
expert requirement, so every extra or repeated item counts against us; this check is meant to cut those. Its risk:
it may also drop a few real obligations.

# Technical

1. Input: `devansh-llm-clause-filter-writer` predictions (rules selection, opus 5.5 clause filter on shall-clauses,
   strict writer splitting clauses into single obligations).
2. Dedupe (`refine.dedupe`): drop a requirement whose normalised text repeats one already kept in the same regulation,
   or whose word set has Jaccard >= 0.9 with one kept from the same paragraph (one-to-one matching: repeats can only be
   false positives).
3. Verifier (`refine.verify`): `claude-opus-5-5`, effort medium, structured output `{id, keep}`, batches of 30 sorted by
   regulation and page so neighbours are judged together; product-neutral drop rules (missing function / variant,
   definition or bare condition, authority procedure, test-procedure step, repeat). Undecided items are kept.
4. Scored with `bench.py` (citations) and `req_judge.py` (requirement level, the platform's main score) on
   dev-rear-lamp and holdout-acpe; adopt only if requirement F2 improves on both.
