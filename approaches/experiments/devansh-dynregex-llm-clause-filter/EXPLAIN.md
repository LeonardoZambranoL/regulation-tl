# In plain words

Nothing is hand-written for the product. Claude reads only the product description (not the list of rulebooks, not the answers) and writes search patterns for its functions and parts, like "stop lamp" or "retro-reflect". Those patterns are searched in the title and scope of all 55 rulebooks; every rulebook that matches is picked, and older rulebooks replaced by newer ones are dropped. Then one Claude agent reads every rule that says something "shall" be done in the picked rulebooks and answers yes or no for this product. Its weakness: the patterns also catch a few rulebooks that do not apply, so the agent must reject their rules.

# Technical

1. Regulation selection: `regselect` `llm_regex`: `claude-opus-5-5` gets only `spec.md` and returns 6-20
   case-insensitive regexes for the product's functions, components, installation and electronics (generic words
   forbidden); invalid regexes are dropped; each regulation whose title + paragraph 1 scope matches any pattern is
   selected; then the supersession and vehicle-category filters. Cached per spec in `devansh-toolkit/.cache`.
2. Candidates: every clause of the selected regulations in `data-ingestion/clauses` matching `\b(shall|must)\b`.
3. Classifier: single agent, `claude-opus-5-5` effort medium, structured output, batches of 40, cached per batch
   (the devansh-llm-clause-filter prompt).
4. Output: every kept clause as one requirement; no size cut.
