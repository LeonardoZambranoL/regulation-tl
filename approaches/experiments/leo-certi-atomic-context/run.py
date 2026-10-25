"""Run the isolated Certi atomic-context experiment from the repository root."""
import argparse
from pathlib import Path
from certi.run import run_pipeline

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["dev-rear-lamp", "holdout-acpe", "heldout-front-bumper"], default="heldout-front-bumper")
    args = parser.parse_args()
    filename = {"dev-rear-lamp": "predictions.json", "holdout-acpe": "predictions-holdout-acpe.json",
                "heldout-front-bumper": "predictions-heldout-front-bumper.json"}[args.case]
    print("Sonnet, 2 workers. Cold run cost is not yet measured; this executes all six stages. Responses are cached.", flush=True)
    run_pipeline(case_arg=args.case, out_path=HERE / "outputs" / filename)
