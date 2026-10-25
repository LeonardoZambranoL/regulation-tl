# In plain words

Claude first builds the same detailed product profile used by `devansh-profile-faithful-v2`, using the written
specification and exploded-view image. It uses v2's regulation selection and keeps table, figure and appendix labels out
of the initial clauses it judges for relevance. If any remaining clause on a page is judged relevant, this variant
includes every parsed clause that touches that page and writes exactly one JSON requirement for each. Its main weakness
is that neighbouring headings, definitions, administrative text and unrelated rules are forced into the output too,
which is likely to lower precision. Page expansion can also include a table-labelled clause when it shares a selected
page.

# Technical

1. Use a fresh LLM cache at `approaches/experiments/leo-greedy-profile-faithful/.cache`.
2. Build the product profile with `claude-sonnet-5-5`, effort `high`, from `spec.md` and the case image when present.
3. Select regulations with the toolkit's `combined` rules, using the original specification so profile wording does
   not spuriously select more regulations.
4. Create `shall+implicit` seed candidates, excluding paragraph labels starting with `Table`, `Figure` or
   `Appendix` as in v2. Classify with `claude-sonnet-5-5`, effort `medium`, using the profile-augmented specification.
5. Mark every `(regulation, version, page)` touched by an applicable seed clause as relevant. Expand to every distinct
   parsed clause from the selected regulations whose `pages` metadata intersects those relevant pages. A clause that
   spans multiple selected pages is still included only once, in original corpus order. Expansion can include labels
   excluded from seed candidates.
6. Write with `claude-sonnet-5-5`, effort `medium`, in batches of eight. The structured response requires one non-empty
   string for every clause ID. Missing or duplicate IDs are retried individually. The writer keeps the clause's scope,
   values, conditions and alternatives, but combines them into one requirement rather than splitting or dropping it.
7. Skip v2's rank/drop refinement and restatement merge because either could remove entries and break the
   one-clause/one-output invariant. Output size equals the expanded distinct-clause count, up to 5,000.
8. No scores have been produced. This variant inherits v2's medium overfit risk and the holdout exposure disclosed in
   v2's risk declaration; whole-page expansion was set before benchmarking this variant.
9. Run the dev case from PowerShell with `python approaches/experiments/leo-greedy-profile-faithful/run.py`; add
   `--case both` to run the holdout too. The runner reports elapsed time and token-based spend after each response,
   using published Sonnet 5.5 rates.
