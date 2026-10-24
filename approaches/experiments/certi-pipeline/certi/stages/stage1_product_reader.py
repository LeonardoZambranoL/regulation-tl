"""Stage 1 — Product Reader (vision + text, 1 deterministic LLM call)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..llm import CachedLLMClient
from ..schemas import STAGE1_JSON_SCHEMA, ProductReaderOutput
from .stage0_load import LoadedCorpus


def run_stage1(
    corpus: LoadedCorpus,
    llm: CachedLLMClient,
    config: dict[str, Any],
    run_dir: Path | None = None,
) -> ProductReaderOutput:
    model = config["models"]["stage1_product_reader"]
    prompt_file = config["prompts"]["stage1_product_reader"]

    payload = {
        "case_id": corpus.case_id,
        "spec_markdown": corpus.spec_text,
        "has_exploded_view_image": corpus.image_path is not None,
    }

    raw = llm.call_json(
        stage="stage1_product_reader",
        model=model,
        prompt_file=prompt_file,
        user_payload=payload,
        schema=STAGE1_JSON_SCHEMA,
        image_path=corpus.image_path,
        max_tokens=6000,
    )
    out = ProductReaderOutput.model_validate(raw)

    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "stage1_product.json").write_text(
            out.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    return out
