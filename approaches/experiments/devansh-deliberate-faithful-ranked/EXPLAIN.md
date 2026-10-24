# In plain words

Instead of judging rules one at a time, an agent reads each section of a rulebook the way an expert does: the whole
section at once, with its numbered structure, and thinks before choosing. It asks which of the product's functions the
section is about and which features the product description actually mentions, then picks the exact numbered rule that
states each obligation (the line with the value, not the heading above it), and skips branches for options the product
does not have. Every pick comes with a one-line reason we can check. The chosen rules then go through the faithful
writer and the 1-5 ranker. Weakness: it costs more (one careful, thinking call per section group).

# Technical

1. Regulation selection: `regselect` `combined` (rules + supersession + vehicle-category filters).
2. Deliberate selection (`deliberate.select_clauses`): every clause of the selected regulations (no shall filter),
   grouped into sections (body: first two number levels; annexes: annex + part + first number), consecutive sections
   packed into windows of at most 45 clauses in document order (77 windows on dev, 26 on holdout-acpe); one
   `claude-opus-5-5` call per window, adaptive thinking, effort high, structured output `{id, reason}`; guidance:
   choose the most specific clause carrying each obligation, parents only when their own text states it, obligations
   without "shall" count, skip unstated features / CoP / references / test-procedure steps / vehicle functions.
   Reasons saved to `outputs/*-clause-reasons.json`.
3. Writer `write.PROMPTS["faithful"]`, then `refine --mode rank --drop-at-or-below 1`.
4. Scored with `bench.py` (clause F2 shows selection quality directly) and `req_judge.py`, dev and holdout-acpe.
