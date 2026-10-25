# Technical explanation: regulation discovery and requirement extraction

Our main-challenge approach turns a product specification and engineering drawing into a list of applicable regulatory requirements. Each output requirement carries a regulation identifier, its base-version label, a PDF page and a paragraph citation. The implementation is in [`approaches/experiments/certi-pipeline`](../../approaches/experiments/certi-pipeline).

The pipeline separates two decisions: **which regulations govern the product**, and **which individual obligations within those regulations apply**. A relevant regulation can contain many clauses for other functions, vehicle categories or approval situations, so regulation selection alone is not enough.

## 1. Prepare the regulatory corpus

The pipeline reads the repository's pre-parsed base regulations from `data-ingestion/clauses/` and combines them with the official regulation index. It retains clause text, paragraph labels, page information, annex structure and available subparagraph citations.

The loader applies deterministic repairs for known parsing anomalies, including detached table labels and incorrectly interpreted annex or subparagraph boundaries. A clause lookup and subparagraph mapping support later citation checks. These repairs improve the available evidence but cannot guarantee that every table or layout-dependent provision was extracted correctly.

The base version matters: a requirement must cite the version against which the challenge is evaluated, rather than silently mixing base and latest regulation pages.

## 2. Understand the product

The product reader sends the specification and, when available, the exploded-view drawing to Claude. The current configuration uses `claude-opus-5-5` for this stage.

Its structured output describes the product, vehicle categories, electronic content, component names and functions, interfaces, safety relevance, search queries and assumptions. Component evidence is labelled as coming from the specification, drawing or both. This profile lets subsequent stages distinguish the primary assembly from its embedded functions—for example, a mechanical assembly may also contain lighting or electronic components with additional regulatory obligations.

The product profile is a model interpretation, not an independently verified bill of materials. An incorrect assumption can affect both regulation selection and clause applicability.

## 3. Select governing regulations

The pipeline generates up to 24 distinct queries from the overall product, its component functions and the reader's suggested search terms. It retrieves up to 30 clause matches per query, aggregates evidence by regulation, and combines retrieval with domain rules that propose relevant regulatory families.

The configured search uses BM25+ word matching with bigrams. The retrieval implementation also supports Gemini embeddings and reciprocal-rank fusion, but **dense embedding retrieval is disabled in the current configuration**. It should therefore not be described as an active semantic-vector search in this configuration.

The candidate pool includes the leading retrieved regulations and regulations triggered by domain rules. The configured candidate limit is 12, with rule-triggered candidates retained beyond that limit. Claude Opus reviews candidate titles, scope excerpts, vehicle categories, supersession metadata and retrieved evidence against the product profile. It returns applicability, confidence, matched components, supporting paragraphs and a reason.

Applicable decisions meeting the configured confidence threshold of 0.65 proceed to deterministic category and supersession checks. The latter avoids retaining older regulations when a selected consolidated regulation explicitly supersedes them. The gate records selected and rejected regulations with their evidence and explanations.

## 4. Extract individual obligations with a coverage ledger

For the selected regulations, the extractor processes clause batches in document order. The default configuration uses `claude-sonnet-5-5`, up to 25 clauses or approximately 14,000 source characters per batch, and eight workers.

Each reviewed clause receives a structured decision: `extracted`, `not_applicable` or `not_an_obligation`, together with a reason. Extracted entries include requirement text, an available subparagraph citation, obligation type, applicability conditions, measurability and a short source quotation. The intended granularity is one self-contained engineering obligation per entry, preserving numerical constraints, units and exceptions.

A ledger tracks processing status for every clause in the selected regulations. Trivial non-obligation material can be classified by code; the model processes the remaining candidates. A second pass addresses clauses left unreviewed. **Complete clause accounting does not prove complete obligation extraction**: a reviewed clause can still contain an overlooked obligation or an incorrect applicability decision.

The base implementation sends at most 6,000 characters of each clause to extraction. Its prompts also contain regulation-specific inclusion and exclusion guidance. These choices bound cost and scope, but can reduce recall for long provisions or duties outside the prescribed categories.

## 5. Verify applicability, faithfulness and requirement boundaries

Before final output, deterministic checks resolve citations against the loaded source clauses and regulation index. A bounded Sonnet verifier then reviews candidate requirements with the product profile and source text, returning `KEEP`, `FIX`, `SPLIT` or `DROP`.

It checks whether the source supports the statement, whether the obligation applies to the product, and whether independent obligations need separate entries. Repairs aim to restore missing conditions or correct values; splitting aims to support one-to-one comparison with expert requirements. The configured threshold for dropping a clearly inapplicable item is 0.95, while borderline cases are generally retained to protect recall.

The base pipeline additionally applies deterministic applicability filters, similarity-based deduplication and output transformations, including syntactic splitting and a regulation-specific pulse-table expansion. These are implementation heuristics rather than independent legal verification. They can remove valid obligations, preserve duplicates or alter requirement boundaries. The verifier also sees a truncated source excerpt, so source coverage remains a limitation.

## 6. Produce a traceable submission

The final JSON contains `team_id`, `case_id` and `requirements`. Each requirement has a unique ID, its text and a citation containing regulation, base version, page and paragraph. The output is checked with the official validator before completion.

Run artifacts preserve the product profile, regulation-gate decisions, coverage ledger, verification actions, richer requirement metadata and execution summary. Model responses are cached using the model, prompt content, schema, input payload and image identity. Repeated runs can reuse unchanged responses; recoverable request or validation failures have bounded retries.

These records make decisions reviewable: an engineer can inspect why a regulation was selected, why a clause was excluded, and how a requirement was repaired. Schema and citation checks establish structural consistency, not semantic correctness.
