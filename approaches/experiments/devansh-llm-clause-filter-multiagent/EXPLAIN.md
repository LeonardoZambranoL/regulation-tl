# In plain words

The same checklist as devansh-llm-clause-filter picks the rulebooks (here 4 of the 55). Then three Claude agents check each other's work so that no applicable rule is missed. Agent A is a strict engineer: it keeps a rule only if it clearly applies to this product. Agent B is a completeness auditor: it keeps every rule that could apply and only drops clear misses. When A and B disagree, agent C, a senior adjudicator, reads the rule and both verdicts and makes the final call. Rules both keep are handed in, rules both drop are left out. Its weakness: the checklist was written while looking at this practice product.

# Technical

1. Regulation selection: `regselect` `combined` (about 35 hand-written regex rules + supersession and
   vehicle-category filters), identical to devansh-llm-clause-filter.
2. Candidates: every clause of the selected regulations in `data-ingestion/clauses` matching `\b(shall|must)\b`.
3. Multi-agent review (`classify.classify_multi`), all `claude-opus-5-5` with structured JSON output, batches of
   40 clauses (25 for the adjudicator), 6 parallel requests, cached per batch:
   - Agent A, strict applicability (the single-agent prompt, effort medium);
   - Agent B, completeness auditor ("answer true unless clearly not applicable", effort medium);
   - Agent C, adjudicator (effort high), only for clauses where A and B disagree, sees both verdicts.
   Final: A = B -> that verdict; A != B -> C's verdict. Agreement counts are in `outputs/review-report.json`.
4. Output: every kept clause as one requirement (clause text, first page, normalised paragraph); no size cut.
