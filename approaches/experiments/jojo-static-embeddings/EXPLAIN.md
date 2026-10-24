# In plain words

The input is a product specification and the fixed set of regulation texts.
The program reuses the team's saved numerical descriptions of the source passages and organizes the passages with their surrounding rules.
Claude first checks which regulations may apply, then reads every clause in those regulations and proposes requirements with source quotes.
A separate pass checks each proposal before it enters the output, while uncertain decisions remain visible.
The main weakness is that the initial regulation selection and the text extracted from tables can still be wrong or incomplete.

# Technical

1. Shared clause JSON and `gemini-embedding-2-preview` vectors, 26,769 rows × 768 dimensions; validate all citation metadata, normalize vectors and hash inputs.
2. Build source-only ancestor/reference catalogue; lexical eight-seed document similarity and RRF k60 prioritize work without removing clauses.
3. `claude-sonnet-5-5` quotes every regulation's scope decision; include uncertain regulations. No fixed regulation allowlist.
4. Assess all selected clauses, no page cap or cross-encoder; 24 clauses / 60,000 target characters per batch, four concurrent requests.
5. Independently verify proposals against complete source/context; retain only supported requirements, with full decision and budget audit.
6. Same frozen inference rules on development and unseen specifications (only a budget-reserve CLI was added before scoring); record scores after generation. High overfit risk because the architectural revision was informed by earlier development results.

7. Final development: page F2 0.842619, clause F2 0.628971, regulation F2 0.952381; 412 exported requirements. Held-out clause recall 0.701754, 508 requirements; Robust 0.772187. Citation scores do not establish semantic correctness. Both cases retain unresolved decisions, with no final budget-limited gaps.
