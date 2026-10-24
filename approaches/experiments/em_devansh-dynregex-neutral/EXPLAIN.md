# In plain words

Same as devansh-dynregex-allclauses-neutral: Claude writes search patterns from the product description to pick the rulebooks, and a Claude reviewer with a product-neutral prompt says yes or no to rules. The original showed Claude every rule in those rulebooks. This version shows it every rule that says "shall", plus the 300 other rules that the team's shared meaning database finds closest to the product description. The question: can the database replace "read everything"? Its weakness: a right rule that is neither "shall" nor close in meaning is never seen.

# Technical

1. Regulation selection: `regselect` `llm_regex` (cached per spec).
2. Candidates (`shall+db`): every `\b(shall|must)\b` clause of the selected regulations, plus the 300 best non-shall clauses of the same regulations from the team's shared vector database (`data-ingestion/.cache/lancedb`, `gemini-embedding-2-preview`, 768 dims, exact cosine; retriever `shared_db`), queries `spec_queries()`, RRF (k0 60).
3. Classifier: single agent, `claude-opus-5-5` effort medium, structured output, batches of 40, the `neutral` prompt, cached per batch.
4. Output: every kept clause as one requirement; no size cut.
5. Scores: see the README "Results" section and the dashboard.
