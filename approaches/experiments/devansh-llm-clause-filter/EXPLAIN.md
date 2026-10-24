# In plain words

Picture the 55 UN Regulations as a library of rulebooks. First a simple checklist reads the product description
(lamps, a reflector, LEDs on a circuit board) and picks the rulebooks that apply: here 4 of the 55. Then Claude reads
every sentence in those 4 rulebooks that says something "shall" be done (about 1,200 of them) and answers one question
for each: does this rule apply to our rear lamp, yes or no? Every "yes" is handed in as a requirement, with the page and
paragraph it came from. It finds almost every right page, but it also says "yes" to some rules the experts did not list.

# Technical

1. Regulation selection: `regselect` method `combined`: about 35 regex rules map spec terms to regulation families,
   then a supersession filter (R148 / R149 / R150 list the regulations they consolidate in their introduction) and a
   vehicle-category filter from each regulation's paragraph 1 scope. Dev: R48, R148, R150, R10.
2. Candidates: every clause of those regulations in `data-ingestion/clauses` matching `\b(shall|must)\b` (1,240 on dev).
3. Classifier: `claude-opus-5-5`, effort medium, structured output (JSON schema `{id, applies}`), batches of 40 clauses
   (text cut at 900 characters) with the full spec and an include / exclude rubric, 6 parallel requests, cached per batch.
4. Output: every `applies = true` clause as one requirement (clause text, first page, normalised paragraph); no ranking
   and no size cut (308 on dev).
5. Dev: page P 0.54 / R 0.98 / F2 0.844, clause F2 0.619, regulation F2 1.0. Overfit risk medium: the rules and the
   rubric were written while looking at the dev product.
