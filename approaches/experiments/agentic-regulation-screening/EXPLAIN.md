# In plain words

One Opus agent inspects each regulation to decide whether it could apply to the product. It starts with the regulation's scope and first clauses, and can search or continue reading before deciding. Regulations it selects or remains unsure about are kept. Sonnet agents then read every clause in those regulations and propose applicable requirements, followed by a separate Sonnet verification pass. A mistaken clear rejection can still hide an applicable regulation.

# Technical

1. Load all 26,769 parsed clauses in the currently indexed 56 base regulation/version groups. Read the product specification only; never read expected answers. No embeddings, vector database, Gemini API, fixed regulation list, or case-specific keywords.
2. Run one `claude-opus-5-5` screening conversation per regulation, 10 concurrently. Supply the title, identifiable scope, first 8 clauses, and at most 40,000 initial characters. Native tools are regulation-local sequential reading, lexical search, and arbitrary chunked clause reading. Budgets: 6 rounds, 12 calls; retry failed tasks twice.
3. Retain `select` and `uncertain` decisions. Also retain failed screening tasks while recording the error. Remove only `reject` decisions. Save exact specification evidence, confidence, topics, API turns and tool traces.
4. Fully assess all retained clauses with `claude-sonnet-5-5`, 10 workers, batches of at most 12 clauses/14,000 target characters, 24,000 context characters, and 4 rounds/8 cross-corpus lexical tool calls. Each clause is assigned once and can emit only its own obligations.
5. Verify proposed requirements independently with `claude-sonnet-5-5`; keep supported candidates, retain duplicates, and validate the official schema. Save predictions, screening, diagnostics and estimated costs separately.
6. Dev run `37ec3cfc2ef94836ade4be35cadc585d`: 9 regulations, 5,107 assessed clauses, 616 exported requirements, estimated cost $21.7112. Page P/R/F1/F2 = 0.3355/0.9623/0.4976/0.7005; clause = 0.1412/0.6860/0.2341/0.3871; regulation = 0.4444/1.0000/0.6154/0.8000. No holdout score and no dev tuning. Medium overfitting risk; the dominant generalization risk is a regulation-level screening false negative, while the observed dev weakness is low clause precision.
