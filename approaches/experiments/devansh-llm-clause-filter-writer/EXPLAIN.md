# In plain words

The platform compares our requirements one by one with the experts' list, and every expert requirement is a single
obligation in one sentence ("The markings shall be clearly legible and indelible."). We used to hand in whole clauses,
which often hold several obligations (a list, a table, one value per test level) plus headings and numbers, so at most
one obligation per clause could ever match. This version keeps the same picks as devansh-llm-clause-filter (a checklist
picks the rulebooks, Claude keeps the rules that apply) and adds one step: Claude rewrites every kept rule into the
single obligations it puts on the product, and drops lab procedures, sampling and paperwork. Its weakness: if the
rule-picking step misses a rule, the writer cannot bring it back.

# Technical

1. Regulation selection: `regselect` `combined` (rules + supersession + vehicle-category filters). Dev: R48, R148,
   R150, R10; unseen ACPE: R10, R175.
2. Clause filter: every `\b(shall|must)\b` clause of those regulations, judged by `claude-opus-5-5` (effort medium,
   batches of 40, the devansh-llm-clause-filter prompt). Dev: 308 of 1,240 kept.
3. Writer (`retrieval/write.py`, prompt `strict`): `claude-opus-5-5` effort medium, batches of 8 clauses, each with its
   parent clause (for the subject) and the spec; returns 0..n one-sentence obligations per clause (subject + shall +
   constraint + condition, the regulation's wording and values, lists / table rows split, no headings or numbers);
   drops definitions, scope lines, authority and administrative duties, absent functions, laboratory test procedure
   details, conformity-of-production sampling and documentation procedures. Each requirement keeps its clause's citation.
4. Output: 328 requirements on dev (188 on ACPE), `team_id` `team-11`.
5. Requirement level (local judge `approaches/benchmarking/req_judge.py`, which reproduced the platform's score of the
   uploaded raw-clause file within one requirement): dev P 0.448 / R 0.774 / **F2 0.676** (raw clauses: 0.338 / 0.547 /
   0.487); ACPE F2 0.390 (raw 0.383). Page P 0.680 / R 0.962, regulation 1.0. Overfit risk medium (see `risk.json`).
