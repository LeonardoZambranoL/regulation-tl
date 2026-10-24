# In plain words

Same as devansh-dynregex-llm-clause-filter: Claude writes search patterns from the product description to pick the rulebooks, then judges every "shall" rule in them. New: the team's shared meaning database also finds the 300 rules without "shall" that are closest to the product description, and Claude judges those too, so obligations written as specs, tables or test steps are no longer invisible. Its weakness: extra candidates also bring extra false "yes" answers.

# Technical

1. Regulation selection: `regselect` `llm_regex` (cached per spec).
2. Candidates: every `\b(shall|must)\b` clause of the selected regulations (unchanged order, cached decisions reused), plus the 300 best non-shall clauses from the team's shared vector database (`data-ingestion/.cache/lancedb`, table `clauses`: 26,769 clause vectors, `gemini-embedding-2-preview`, 768 dims); queries embedded with the same model via `data-ingestion/gemini_embedding.py`, exact cosine search restricted to the selected regulations (retriever `shared_db` in devansh-toolkit); queries `spec_queries()`, RRF (k0 60).
3. Classifier: single agent, `claude-opus-5-5` effort medium, structured output, batches of 40, cached per batch.
4. Output: every kept clause as one requirement; no size cut.
5. Scores: see the README "Results" section and the dashboard.
