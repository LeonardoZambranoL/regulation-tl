"""Main entry point for Certi 6-stage deterministic pipeline.

Usage:
    .venv/bin/python -m certi.run --case dev-rear-lamp --out outputs/predictions.json
    .venv/bin/python -m certi.run --case holdout-acpe --out outputs/predictions-holdout-acpe.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .llm import CachedLLMClient
from .retrieval import HybridRetriever
from .stages.stage0_load import load_stage0
from .stages.stage1_product_reader import run_stage1
from .stages.stage2_gate import run_stage2_gate
from .stages.stage3_extract import run_stage3_and_4
from .stages.stage5_verify import run_stage5_and_6

EXP_DIR = Path(__file__).resolve().parent.parent


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or (EXP_DIR / "config.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_pipeline(
    *,
    case_arg: str | Path,
    out_path: Path,
    config_path: Path | None = None,
    use_cache: bool = True,
    run_id: str | None = None,
    skip_verifier: bool = False,
) -> dict[str, Any]:
    t0 = time.time()
    config = load_config(config_path)
    if skip_verifier:
        config["verification"]["enabled"] = False

    # Stage 0 — Load
    print(f"[Stage 0] Loading case {case_arg!r} and 56 parsed UN Regulations...")
    corpus = load_stage0(case_arg)

    if run_id is None:
        cfg_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()[:8]
        run_id = f"{corpus.case_id}_{cfg_hash}"
    run_dir = EXP_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    llm = CachedLLMClient(use_cache=use_cache)

    # Stage 1 — Product Reader
    print(f"[Stage 1] Running Product Reader ({config['models']['stage1_product_reader']})...")
    product = run_stage1(corpus, llm, config, run_dir=run_dir)
    print(f"          Product: {product.product}")
    print(f"          Categories: {product.vehicle_categories} | Electronics/ESA: {product.has_electronics} | Parts: {len(product.parts)}")

    # Stage 2 — Regulation Gate
    print(f"[Stage 2] Running Hybrid Retrieval + Regulation Gate ({config['models']['stage2_regulation_gate']})...")
    retriever = HybridRetriever(
        corpus,
        llm_client=llm,
        k1=config["retrieval"].get("bm25_k1", 1.2),
        b=config["retrieval"].get("bm25_b", 0.75),
        delta=config["retrieval"].get("bm25_delta", 1.0),
        bigrams=config["retrieval"].get("bm25_bigrams", True),
        rrf_k0=config["retrieval"].get("rrf_k0", 60),
        use_dense=config["retrieval"].get("use_dense_embeddings", True),
    )
    selected_regs, gate_report = run_stage2_gate(
        corpus, product, retriever, llm, config, run_dir=run_dir
    )
    print(f"\n========================================================")
    print(f"FINAL SELECTED REGULATIONS ({len(selected_regs)}): {selected_regs}")
    print(f"========================================================\n")

    # Stage 3 & 4 — Exhaustive Extraction & Coverage Ledger
    print(f"[Stage 3 & 4] Running Exhaustive Clause Extraction ({config['models']['stage3_extractor']}) on {selected_regs}...")
    extracted_items, stage34_report = run_stage3_and_4(
        corpus, product, selected_regs, llm, config, run_dir=run_dir
    )
    for reg, cov in stage34_report["coverage_by_regulation"].items():
        print(f"          {reg}: {cov['coverage_pct']}% reviewed ({cov['status_counts']})")
    print(f"          Total extracted obligations: {len(extracted_items)}")

    # Stage 5 & 6 — Verification & Submission Output
    print(f"[Stage 5 & 6] Running Bounded Verifiers & Official Validation -> {out_path}...")
    submission_doc, stage5_report = run_stage5_and_6(
        corpus,
        product,
        extracted_items,
        gate_report,
        llm,
        config,
        out_path=out_path,
        run_dir=run_dir,
    )

    elapsed = round(time.time() - t0, 2)
    summary = {
        "run_id": run_id,
        "case_id": corpus.case_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "selected_regulations": selected_regs,
        "extracted_count": len(extracted_items),
        "final_requirements_count": len(submission_doc.requirements),
        "output_path": str(out_path),
        "llm_stats": llm.stats,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"[Done] Wrote {len(submission_doc.requirements)} validated requirements to {out_path} in {elapsed}s")
    print(f"       LLM API calls: {llm.stats['api_calls']} (cache hits: {llm.stats['cache_hits']}) | Emb API calls: {llm.stats['emb_api_calls']} (cache hits: {llm.stats['emb_cache_hits']})")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="dev-rear-lamp", help="Case directory or name (e.g. dev-rear-lamp, holdout-acpe)")
    ap.add_argument("--out", type=Path, default=EXP_DIR / "outputs" / "predictions.json", help="Output submission JSON path")
    ap.add_argument("--config", type=Path, default=EXP_DIR / "config.yaml", help="Config YAML path")
    ap.add_argument("--no-cache", action="store_true", help="Bypass LLM and embedding disk cache")
    ap.add_argument("--skip-verifier", action="store_true", help="Skip Stage 5 LLM verifier (baseline ablation)")
    ap.add_argument("--run-id", default=None, help="Explicit run ID under runs/<run_id>")
    args = ap.parse_args(argv)

    run_pipeline(
        case_arg=args.case,
        out_path=args.out,
        config_path=args.config,
        use_cache=not args.no_cache,
        run_id=args.run_id,
        skip_verifier=args.skip_verifier,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
