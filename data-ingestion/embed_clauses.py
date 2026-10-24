"""Generate clause vectors with the same shared Gemini call used by retrieval."""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from tqdm import tqdm

from gemini_embedding import embed_text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load_rows(folder, index_path):
    index = json.loads(index_path.read_text(encoding="utf-8"))
    titles = {item["regulation"]: item.get("title", "") for item in index}
    rows = []
    for path in sorted(folder.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for clause in document["clauses"]:
            paragraph = " ".join(str(clause.get("paragraph") or "").replace("/", " ").split())
            rows.append({
                "regulation": document["regulation"],
                "version": document["version"],
                "page": clause["pages"][0],
                "paragraph": paragraph,
                "embedding_text": (
                    f"{document['regulation']} {titles.get(document['regulation'], '')}. {paragraph}\n"
                    f"{clause['text'].replace(chr(13) + chr(10), chr(10))}"
                ),
            })
    if not rows:
        raise ValueError("No clause records found")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemini-embedding-2-preview")
    parser.add_argument("--dim", type=int, default=768)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--clauses", type=Path, default=HERE / "clauses")
    parser.add_argument("--index", type=Path, default=ROOT.parent / "industrial-ai-hackathon/regulations/index.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.dim < 1 or args.workers < 1:
        parser.error("dim and workers must be positive")

    load_dotenv(ROOT / ".env")
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        parser.error("Set GEMINI_API_KEY in the repository .env")
    rows = load_rows(args.clauses, args.index)
    output = args.output or HERE / "embeddings" / f"{args.model}_d{args.dim}_n{len(rows)}.npz"

    vectors = np.empty((len(rows), args.dim), dtype=np.float32)
    with ThreadPoolExecutor(max_workers=args.workers) as pool, tqdm(total=len(rows), unit="clause") as progress:
        futures = {
            pool.submit(embed_text, row["embedding_text"], model=args.model,
                        dimensions=args.dim, api_key=key): i
            for i, row in enumerate(rows)
        }
        for future in as_completed(futures):
            vectors[futures[future]] = future.result()
            progress.update(1)

    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        embeddings=vectors.astype(np.float16),
        regulations=np.asarray([row["regulation"] for row in rows]),
        versions=np.asarray([row["version"] for row in rows]),
        pages=np.asarray([row["page"] for row in rows], dtype=np.int32),
        paragraphs=np.asarray([row["paragraph"] for row in rows]),
    )
    query = embed_text("stop lamp luminous intensity requirements", model=args.model,
                       dimensions=args.dim, api_key=key)
    best = np.argsort(vectors @ query)[-3:][::-1]
    print(f"Wrote {output} with shape {vectors.shape}")
    print("Sanity-search rows:", ", ".join(str(int(i)) for i in best))


if __name__ == "__main__":
    main()
