# In plain words

Built to work on any product, not just the rear lamp. Claude reads only the product description and writes search
patterns for its functions and parts; every rulebook whose title and scope match is picked (older rulebooks replaced
by newer ones are dropped). Then one Claude agent reads every single rule in the picked rulebooks, not just the ones
containing "shall", because many rules are written as plain specifications ("Height: not less than 250 mm") or as
"is not permitted". For each rule it answers: does this apply to the product described, yes or no? Every "yes" is
handed in with its page and paragraph. Its weakness: it reads two to three times more rules, so it costs more, and it
can still keep rules from rulebooks that matched by accident.

# Technical

1. Regulation selection: `regselect` `llm_regex`: `claude-opus-5-5` sees only `spec.md` and returns 6-20
   case-insensitive regexes (generic words forbidden); a regulation is selected when any pattern matches its title or
   paragraph 1 scope; then supersession and vehicle-category filters. Cached per spec.
2. Candidates: **every** clause of the selected regulations in `data-ingestion/clauses` (`"candidates": "all"`), no
   shall / must filter (dev: 6,080 clauses from 8 regulations; holdout-acpe: 5,349 from 10).
3. Reviewer: one `claude-opus-5-5` agent, effort medium, structured output, batches of 40, 6 parallel requests, cached
   per batch, with the product-neutral prompt (`classify.NEUTRAL_INSTRUCTIONS`): no product or function names, explains
   implicit obligations, "decide from the spec, not from what products of this kind usually have".
4. Output: every kept clause as one requirement (clause text, first page, normalised paragraph); no size cut.
5. Evaluated on dev-rear-lamp and on the unseen holdout-acpe case (R175 answer key); see the dashboard.
