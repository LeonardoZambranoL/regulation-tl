"""Import the existing clause vectors and text into a local LanceDB table."""

import argparse
import json
from pathlib import Path

import lancedb
import numpy as np
import pyarrow as pa

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def paragraph_key(value):
    return " ".join(str(value or "").replace("/", " ").split())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", type=Path, default=ROOT / "data-ingestion/embeddings/gemini-embedding-2-preview_d768_n26769.npz")
    parser.add_argument("--clauses", type=Path, default=ROOT / "data-ingestion/clauses")
    parser.add_argument("--db", type=Path, default=HERE / ".cache/lancedb")
    parser.add_argument("--replace", action="store_true", help="Replace an existing clauses table instead of refusing to overwrite it")
    args = parser.parse_args()

    with np.load(args.embeddings, allow_pickle=False) as archive:
        vectors = archive["embeddings"].astype(np.float32)
        metadata = {name: archive[name] for name in ("regulations", "versions", "pages", "paragraphs")}
    if vectors.ndim != 2 or not len(vectors) or not np.isfinite(vectors).all():
        raise ValueError("Expected a nonempty matrix of finite embeddings")
    if any(len(values) != len(vectors) for values in metadata.values()):
        raise ValueError("Embedding metadata lengths do not match the vectors")
    if np.any(np.linalg.norm(vectors, axis=1) == 0):
        raise ValueError("Embeddings contain a zero vector")

    # The NPZ uses sorted JSON filename order, then original clause order.
    # Check every row before writing: citation metadata alone is not unique.
    rows = []
    files = sorted(args.clauses.glob("*.json"))
    for path in files:
        document = json.loads(path.read_text(encoding="utf-8"))
        for number, clause in enumerate(document["clauses"]):
            i = len(rows)
            if i >= len(vectors):
                raise ValueError("More clauses than vectors")
            expected = (document["regulation"], document["version"], clause["pages"][0], paragraph_key(clause.get("paragraph")))
            actual = (str(metadata["regulations"][i]), str(metadata["versions"][i]), int(metadata["pages"][i]), paragraph_key(metadata["paragraphs"][i]))
            if expected != actual:
                raise ValueError(f"Vector {i} does not match {path.name}, clause {number}: {actual} != {expected}")
            rows.append({
                "clause_id": f"{path.stem}:{number}",
                "vector_row": i,
                "regulation": document["regulation"],
                "version": document["version"],
                "paragraph": clause.get("paragraph"),
                "pages": clause["pages"],
                "text": clause["text"],
            })
    if len(rows) != len(vectors):
        raise ValueError(f"Found {len(rows)} clauses but {len(vectors)} vectors")

    schema = pa.schema([
        ("clause_id", pa.string()), ("vector_row", pa.int64()),
        ("regulation", pa.string()), ("version", pa.string()),
        ("paragraph", pa.string()), ("pages", pa.list_(pa.int32())),
        ("text", pa.string()),
    ])
    data = pa.Table.from_pylist(rows, schema=schema)
    vector_column = pa.FixedSizeListArray.from_arrays(pa.array(vectors.ravel()), vectors.shape[1])
    data = data.append_column("vector", vector_column)
    print(f"Validated {len(rows):,} clause/vector mappings across {len(files)} files.", flush=True)
    db = lancedb.connect(str(args.db.resolve()))
    table = db.create_table("clauses", data, mode="overwrite" if args.replace else "create")
    if table.count_rows() != len(rows):
        raise RuntimeError("Stored row count does not match the input")

    # Exercise real vector search without an API call or generating new vectors.
    hits = table.search(vectors[0]).distance_type("cosine").select(["clause_id", "_distance"]).limit(1).to_list()
    if not hits or abs(hits[0]["_distance"]) > 0.0001:
        raise RuntimeError("Vector-search sanity check failed")
    print(f"Stored {table.count_rows():,} vectors ({vectors.shape[1]} dimensions) in {args.db.resolve()}")
    print("Table: clauses. Vector-search sanity check passed. No API calls made.")


if __name__ == "__main__":
    main()
