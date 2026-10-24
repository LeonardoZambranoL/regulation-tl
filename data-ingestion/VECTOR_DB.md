# Shared local vector database

This database is shared across experiments. The importer loads existing vectors and clause text; each experiment implements its own retrieval and analysis.

From the repository root, with your virtual environment activated:

```powershell
python -m pip install -r data-ingestion/requirements-vectors.txt
python data-ingestion/import_vectors.py
```

The script reads the existing Gemini NPZ and the clause JSON files, verifies every vector's citation against the clause in the corresponding position, then creates a local [LanceDB](https://lancedb.github.io/lancedb/python/python/) database at `data-ingestion/.cache/lancedb`. No server, API key, or new embeddings are needed. The database is git-ignored; teammates can rebuild it with the same command.

The current corpus and query model is `gemini-embedding-2-preview` at 768 dimensions. The importer records the model in `manifest.json` and refuses a misleading filename/model combination. Query embeddings must use that same preview model; the stored vectors are not rebuilt by experiments.

`embed_clauses.py` and the agentic RAG experiment both call `gemini_embedding.py`. It sends plain text to Google's REST `embedContent` endpoint, requests 768 dimensions, checks the returned vector, and normalizes it. Clause text includes the regulation name, regulation title, normalized paragraph label, and source text. Retrieval sends the agent's plain search query through the same helper. The already-supplied NPZ does not contain client or prompt provenance, so the repository cannot prove that its historical generation used this exact helper.

Each row in the `clauses` table contains `clause_id`, `vector_row`, `regulation`, `version`, `paragraph`, `pages`, `text`, and `vector`. The vector has 768 dimensions, stored as float32 converted from the supplied float16 values. Clause IDs combine the JSON filename stem with the zero-based clause position, so repeated paragraph labels remain separate records.

Import assumes sorted JSON filenames and original clause order, and stops if any citation differs. The NPZ does not contain source-text hashes, so metadata checks cannot detect text changes that leave citations unchanged. Use the original clause files that generated these embeddings.

Re-running refuses to overwrite the table. To rebuild it intentionally, add `--replace`. Optional `--embeddings`, `--clauses`, and `--db` arguments accept alternative paths.

For subsequent searches, embed queries with the same `gemini-embedding-2-preview` model and 768 dimensions, then use `table.search(query_vector).distance_type("cosine").limit(k).to_list()`. Searches currently compare all vectors exactly; no approximate index or retrieval cutoff is configured. Regulation and version fields let the next stage fetch all clauses of a retrieved regulation. The database manifest records the embedding model so experiments can reject incompatible query vectors.

Experiments can open the shared table like this (`repo_root` is the repository's absolute path):

```python
from pathlib import Path
import lancedb

db = lancedb.connect(str(Path(repo_root) / "data-ingestion/.cache/lancedb"))
table = db.open_table("clauses")
hits = table.search(query_vector).distance_type("cosine").limit(100).to_list()
```

Treat the shared table as read-only from experiments. Keep experiment-specific tables and indexes in that experiment's own cache. The importer does not read product specs or answer keys.
