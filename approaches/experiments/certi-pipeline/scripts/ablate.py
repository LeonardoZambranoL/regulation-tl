"""Ablation runner: evaluates cached runs across different Stage 5 verifier strictness, deduplication, and verbatim settings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP_DIR))

from certi.llm import CachedLLMClient  # noqa: E402
from certi.run import load_config  # noqa: E402
from certi.schemas import ExtractedObligation, ProductReaderOutput  # noqa: E402
from certi.stages.stage0_load import load_stage0  # noqa: E402
from certi.stages.stage5_verify import run_stage5_and_6  # noqa: E402
from scripts.eval_main import evaluate_predictions  # noqa: E402


def main() -> int:
    run_dirs = sorted((EXP_DIR / "runs").glob("dev-rear-lamp*"))
    if not run_dirs:
        print("No cached dev-rear-lamp runs found under runs/. Run certi.run first.")
        return 1

    run_dir = run_dirs[-1]
    corpus = load_stage0("dev-rear-lamp")
    product = ProductReaderOutput.model_validate_json((run_dir / "stage1_product.json").read_text(encoding="utf-8"))
    gate_report = json.loads((run_dir / "gate.json").read_text(encoding="utf-8"))
    s3_raw = json.loads((run_dir / "stage3_extracted.json").read_text(encoding="utf-8"))
    extracted_items = [ExtractedObligation.model_validate(x) for x in s3_raw]
    llm = CachedLLMClient(use_cache=True)

    configs_to_test = [
        ("Pass 1+2 only (no Stage 5 LLM verifier)", {"enabled": False, "verbatim": True, "drop_conf": 1.0}),
        ("Stage 5 Verifier (strict drop_conf=0.70)", {"enabled": True, "verbatim": True, "drop_conf": 0.70}),
        ("Stage 5 Verifier (balanced drop_conf=0.80)", {"enabled": True, "verbatim": True, "drop_conf": 0.80}),
        ("Stage 5 Verifier (high-recall drop_conf=0.90)", {"enabled": True, "verbatim": True, "drop_conf": 0.90}),
    ]

    rows = []
    for label, params in configs_to_test:
        cfg = load_config()
        cfg["verification"]["enabled"] = params["enabled"]
        cfg["verification"]["applicability_drop_confidence"] = params["drop_conf"]
        cfg["extraction"]["verbatim_clause_text"] = params["verbatim"]

        tmp_out = EXP_DIR / ".cache" / "ablate_tmp.json"
        run_stage5_and_6(
            corpus, product, extracted_items, gate_report, llm, cfg, out_path=tmp_out, run_dir=None
        )
        rep = evaluate_predictions(tmp_out, case_arg="dev-rear-lamp", run_dir=run_dir)
        m = rep["metrics"]
        rows.append({
            "variant": label,
            "n_reqs": rep["n_submitted_requirements"],
            "reg_f2": m["regulation_level"]["f2"],
            "page_p": m["page_level"]["precision"],
            "page_r": m["page_level"]["recall"],
            "page_f2": m["page_level"]["f2"],
            "clause_p": m["clause_level"]["precision"],
            "clause_r": m["clause_level"]["recall"],
            "clause_f2": m["clause_level"]["f2"],
        })

    print("\n| Variant | Reqs | Reg F2 | Page P | Page R | Page F2 | Clause P | Clause R | Clause F2 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        print(
            f"| {r['variant']} | {r['n_reqs']} | {r['reg_f2']:.4f} | "
            f"{r['page_p']:.4f} | {r['page_r']:.4f} | **{r['page_f2']:.4f}** | "
            f"{r['clause_p']:.4f} | {r['clause_r']:.4f} | **{r['clause_f2']:.4f}** |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
