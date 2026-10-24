# In plain words

Same as devansh-llm-clause-filter: a checklist picks the rulebooks and Claude says yes or no to each rule that says "shall". New: many real obligations are written without "shall" ("Height: not less than 350 mm", test instructions), and the old version never showed them to Claude. Now the team's shared meaning database also finds the 300 non-"shall" rules closest to the product description, and Claude judges those too. Its weakness: more rules to judge means more chances to say "yes" wrongly.

# Technical

1. Regulation selection: `regselect` `combined`.
2. Candidates: every `\b(shall|must)\b` clause of the selected regulations (unchanged, same order, so cached decisions are reused), plus the 300 best non-shall clauses of the same regulations from the team's shared vector database (`data-ingestion/.cache/lancedb`, table `clauses`: 26,769 clause vectors, `gemini-embedding-2-preview`, 768 dims); queries embedded with the same model via `data-ingestion/gemini_embedding.py`, exact cosine search restricted to the selected regulations (retriever `shared_db` in devansh-toolkit); queries `spec_queries()`, RRF (k0 60).
3. Classifier: `claude-opus-5-5`, effort medium, structured output, batches of 40, the devansh-llm-clause-filter prompt, cached per batch.
4. Output: every kept clause as one requirement; no size cut.
5. Scores: see the README "Results" section and the dashboard.
