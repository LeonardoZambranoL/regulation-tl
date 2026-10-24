"""Screen each regulation with one agent, then fully assess selected regulations."""

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from engine import *
from screening import screen_regulation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    challenge = ROOT.parent / "industrial-ai-hackathon"
    parser.add_argument("--spec", type=Path, default=challenge / "cases/dev-rear-lamp/spec.md")
    parser.add_argument("--clauses", type=Path, default=ROOT / "data-ingestion/clauses")
    parser.add_argument("--index", type=Path, default=challenge / "regulations/index.json")
    parser.add_argument("--team-id", default="4TL")
    parser.add_argument("--case-id", default="dev-rear-lamp")
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--output", type=Path, default=HERE / "outputs")
    parser.add_argument("--max-regulations", type=int, help="Screen only the first N regulations for a smoke run")
    parser.add_argument("--max-batches", type=int, help="Assess only the first N selected batches for a smoke run")
    parser.add_argument("--screen-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    integer_keys = ("workers", "batch_size", "batch_characters", "context_characters", "max_tokens",
                    "screening_initial_clauses", "screening_initial_characters",
                    "screening_tool_rounds", "screening_tool_calls")
    for key in integer_keys:
        if type(config.get(key)) is not int or config[key] < 1:
            parser.error(f"{key} must be a positive integer")
    for key in ("max_tool_rounds", "max_tool_calls", "batch_retries"):
        if type(config.get(key)) is not int or config[key] < 0:
            parser.error(f"{key} must be a nonnegative integer")
    for value, name in ((args.max_regulations, "max-regulations"), (args.max_batches, "max-batches")):
        if value is not None and value < 1:
            parser.error(f"--{name} must be positive")
    if any("opus" in config[key].casefold() for key in ("model", "verification_model")):
        parser.error("Opus is reserved for regulation screening; assessment and verification use Sonnet")

    spec = args.spec.read_text(encoding="utf-8")
    if not spec.strip():
        parser.error("Product specification is empty")
    index = load_index(args.index)
    corpus, documents = load_corpus(args.clauses, index)
    titles = {item["regulation"]: item.get("title", "") for item in index}
    screening_documents = documents[:args.max_regulations] if args.max_regulations else documents
    print(f"{len(screening_documents)}/{len(documents)} regulations to screen; one Opus agent each; "
          f"{config['workers']} parallel workers; first {config['screening_initial_clauses']} clauses supplied.")
    if args.dry_run:
        print(f"After screening, every clause in selected/uncertain regulations is assessed with {config['model']} and verified with {config['verification_model']}.")
        print("No embeddings, vector database, API calls, or output writes.")
        return 0

    load_dotenv(HERE / ".env")
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        parser.error("Set ANTHROPIC_API_KEY in .env")
    pricing = json.loads((HERE / "pricing.json").read_text(encoding="utf-8"))
    for model in (config["screening_model"], config["model"], config["verification_model"]):
        if model not in pricing:
            parser.error(f"Add rates for {model} to pricing.json before running")

    previous = args.output / "predictions.json"
    if previous.exists():
        previous.replace(args.output / "predictions.previous.json")
    costs = RunCosts(args.output / "costs.json", pricing)
    screen_config = dict(config, model=config["screening_model"],
                         max_tool_rounds=config["screening_tool_rounds"],
                         max_tool_calls=config["screening_tool_calls"])
    screen_client = Claude(screen_config, spec, None, HERE / ".cache", corpus, costs, "screening")

    screened, screening_errors = {}, []
    with tqdm(total=len(screening_documents), desc="Regulation screening", unit="reg", dynamic_ncols=True) as progress, \
            ThreadPoolExecutor(max_workers=config["workers"]) as pool:
        futures = {
            pool.submit(run_batch, screen_regulation, (entries, titles.get(entries[0]["regulation"], "")),
                        screen_client, "Screening", i + 1): i
            for i, entries in enumerate(screening_documents)
        }
        for future in as_completed(futures):
            i = futures[future]
            try:
                screened[i] = future.result()
            except Exception as error:
                screening_errors.append({"stage": "screening", "regulation": screening_documents[i][0]["regulation"],
                                         "version": screening_documents[i][0]["version"], "error": str(error),
                                         "attempts": getattr(error, "attempts", [])})
                tqdm.write(f"Screening {screening_documents[i][0]['regulation']} failed; it will be fully scanned: {error}", file=sys.stderr)
            finally:
                counts = Counter(row["decision"] for row in screened.values())
                progress.set_postfix(select=counts["select"], uncertain=counts["uncertain"],
                                     reject=counts["reject"], failed=len(screening_errors),
                                     cost=f"${costs.total():.4f}", refresh=False)
                progress.update(1)

    failed_keys = {(row["regulation"], row["version"]) for row in screening_errors}
    selected_keys = {(row["regulation"], row["version"]) for row in screened.values()
                     if row["decision"] != "reject"}
    selected_keys.update(failed_keys)
    selected_documents = [entries for entries in screening_documents
                          if (entries[0]["regulation"], entries[0]["version"]) in selected_keys]
    screening_output = {
        "complete": len(screened) == len(documents) and not screening_errors,
        "available_regulations": len(documents), "screened_regulations": len(screened),
        "selected_regulations": [list(key) for key in sorted(selected_keys)],
        "decisions": [screened[i] for i in sorted(screened)], "errors": screening_errors,
    }
    write_json(args.output / "screening.json", screening_output)
    selected_clause_count = sum(len(entries) for entries in selected_documents)
    print(f"Selected {len(selected_documents)} regulations ({selected_clause_count} clauses); "
          f"Claude cost so far: ${costs.total():.4f}.")
    if args.screen_only:
        return int(bool(screening_errors) or len(screening_documents) != len(documents))

    batches = make_batches(selected_documents, config["batch_size"], config["batch_characters"])
    if args.max_batches:
        batches = batches[:args.max_batches]
    assigned = [clause["id"] for batch in batches for clause in batch]
    assessment_client = Claude(config, spec, None, HERE / ".cache", corpus, costs, "assessment")
    verification_client = Claude(dict(config, model=config["verification_model"]),
                                 spec, None, HERE / ".cache", corpus, costs, "verification")
    diagnostics = {
        "config": config, "started_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version, "seed": None,
        "screening": screening_output,
        "coverage": {"available_clauses": len(corpus), "selected_clauses": selected_clause_count,
                     "assigned_clauses": len(assigned), "complete": False},
        "batches": [], "candidates": [], "verification": [], "errors": list(screening_errors),
    }

    outcomes = {}
    with tqdm(total=len(batches), desc="Clause assessment", unit="batch", dynamic_ncols=True) as progress, \
            ThreadPoolExecutor(max_workers=config["workers"]) as pool:
        futures = {pool.submit(run_batch, assess_batch, (batch, documents, corpus), assessment_client,
                               "Assessment", i + 1): i for i, batch in enumerate(batches)}
        for future in as_completed(futures):
            i = futures[future]
            try:
                outcomes[i] = future.result()
            except Exception as error:
                diagnostics["errors"].append({"stage": "assessment", "batch": i + 1, "error": str(error),
                                              "attempts": getattr(error, "attempts", [])})
                tqdm.write(f"Assessment batch {i + 1} failed: {error}", file=sys.stderr)
            finally:
                progress.set_postfix(ok=len(outcomes), failed=len(diagnostics["errors"]),
                                     cost=f"${costs.total():.4f}", refresh=False)
                progress.update(1)

    candidates, verification_jobs = [], []
    for i in sorted(outcomes):
        outcome = outcomes[i]
        diagnostics["batches"].append({"batch": i + 1, "decisions": outcome["decisions"],
                                       "history": outcome["history"], "attempts": outcome["batch_attempts"]})
        group = []
        for decision in outcome["decisions"]:
            for number, requirement in enumerate(decision["requirements"]):
                candidate = dict(requirement, candidate_id=f"{decision['clause_id']}:r{number}",
                                 assessed_clause_id=decision["clause_id"])
                candidates.append(candidate)
                group.append(candidate)
        for start in range(0, len(group), 12):
            verification_jobs.append((group[start:start + 12], outcome["context"]))
    diagnostics["candidates"] = candidates

    supported, verification_failures = set(), 0
    with tqdm(total=len(verification_jobs), desc="Verification", unit="batch", dynamic_ncols=True) as progress, \
            ThreadPoolExecutor(max_workers=config["workers"]) as pool:
        futures = {pool.submit(run_batch, verify_batch, (group, context, corpus), verification_client,
                               "Verification", i + 1): group
                   for i, (group, context) in enumerate(verification_jobs)}
        for future in as_completed(futures):
            try:
                verified = future.result()
                diagnostics["verification"].append(verified)
                supported.update(result["candidate_id"] for result in verified["results"]
                                 if result["status"] == "supported")
            except Exception as error:
                diagnostics["errors"].append({"stage": "verification",
                    "candidate_ids": [candidate["candidate_id"] for candidate in futures[future]],
                    "error": str(error), "attempts": getattr(error, "attempts", [])})
                verification_failures += 1
                tqdm.write(f"Verification batch failed: {error}", file=sys.stderr)
            finally:
                progress.set_postfix(supported=len(supported), failed=verification_failures,
                                     cost=f"${costs.total():.4f}", refresh=False)
                progress.update(1)

    accepted = [candidate for candidate in candidates if candidate["candidate_id"] in supported]
    submission, links = submission_for(accepted, corpus, args.team_id, args.case_id)
    diagnostics["submission_ids"] = links
    decisions = [decision for outcome in outcomes.values() for decision in outcome["decisions"]]
    assessed_ids = {decision["clause_id"] for decision in decisions}
    screening_complete = len(screened) == len(documents) and not screening_errors
    assessment_complete = len(decisions) == selected_clause_count and assessed_ids == set(assigned)
    diagnostics["coverage"].update({
        "assessed_clauses": len(decisions),
        "unassessed_selected_ids": sorted(set(clause["id"] for entries in selected_documents for clause in entries) - assessed_ids),
        "status_counts": dict(Counter(decision["status"] for decision in decisions)),
        "screening_complete": screening_complete, "assessment_complete": assessment_complete,
        "complete": screening_complete and assessment_complete and not diagnostics["errors"],
    })
    problems = [str(problem) for problem in validate(submission, index=index, strict=True)]
    if len((json.dumps(submission, ensure_ascii=False, indent=2) + "\n").encode()) > MAX_BYTES:
        problems.append("Submission exceeds 5 MiB")
    diagnostics["validation_errors"] = problems
    diagnostics["finished_at"] = datetime.now(timezone.utc).isoformat()
    diagnostics["estimated_cost_usd"] = costs.total()
    write_json(args.output / "diagnostics.json", diagnostics)
    print(f"Estimated Claude cost this run: ${costs.total():.4f} USD (see costs.json)")
    if problems:
        print("Validation failed; predictions.json was not written. See diagnostics.json.", file=sys.stderr)
        return 1
    write_json(args.output / "predictions.json", submission)
    print(f"Wrote predictions.json ({len(accepted)} requirements), screening.json and diagnostics.json")
    if not diagnostics["coverage"]["complete"]:
        print("Run incomplete or partial; see diagnostics.json.", file=sys.stderr)
    return int(not diagnostics["coverage"]["complete"])


if __name__ == "__main__":
    sys.exit(main())
