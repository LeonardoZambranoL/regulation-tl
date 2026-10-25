"""Content-addressed JSON cache for deterministic preparation only."""
import hashlib
import json
import os
import tempfile
from pathlib import Path


def cached_prepare(directory: Path, stage: str, inputs: dict, sources: list[Path], build):
    digest = hashlib.sha256()
    digest.update(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode())
    for source in sources:
        digest.update(source.name.encode())
        digest.update(source.read_bytes())
    path = directory / f"{stage}-{digest.hexdigest()}.json"
    if path.is_file():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved["key"] == digest.hexdigest():
                print(f"[prepare] Reusing cached {stage}", flush=True)
                return saved["result"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    print(f"[prepare] Computing {stage}; subsequent runs will reuse it", flush=True)
    result = build()
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"key": digest.hexdigest(), "result": result}, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result
