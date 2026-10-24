"""Agent-selected vector searches followed by full scans of retrieved regulations."""

from engine import *
from retrieval import SearchTools, open_corpus, plan

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    challenge = ROOT.parent / "industrial-ai-hackathon"
    parser.add_argument("--spec", type=Path, default=challenge / "cases/dev-rear-lamp/spec.md")
    parser.add_argument("--db", type=Path, default=ROOT / "data-ingestion/.cache/lancedb")
    parser.add_argument("--index", type=Path, default=challenge / "regulations/index.json")
    parser.add_argument("--team-id", default="4TL")
    parser.add_argument("--case-id", default="dev-rear-lamp")
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--output", type=Path, default=HERE / "outputs")
    parser.add_argument("--max-batches", type=int, help="Smoke-test subset; diagnostics will mark it partial")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retrieve-only", action="store_true", help="Run planning and retrieval without clause analysis")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    config.setdefault("verification_model", "claude-sonnet-5-5")
    config.setdefault("batch_retries", 2)
    for key in ("workers", "batch_size", "batch_characters", "context_characters", "max_tokens"):
        if type(config[key]) is not int or config[key] < 1:
            parser.error(f"{key} must be a positive integer")
    for key in ("max_tool_rounds", "max_tool_calls", "batch_retries"):
        if type(config[key]) is not int or config[key] < 0:
            parser.error(f"{key} must be a nonnegative integer")
    if args.max_batches is not None and args.max_batches < 1:
        parser.error("--max-batches must be positive")
    if not args.team_id.strip() or not args.case_id.strip():
        parser.error("team-id and case-id cannot be blank")
    spec = args.spec.read_text(encoding="utf-8")
    if not spec.strip():
        parser.error("Product spec is empty")
    index = load_index(args.index)
    try:
        table, corpus, documents = open_corpus(
            args.db, index, config["dimensions"], config["embedding_model"]
        )
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))
    for key in ("regulations_per_query", "evidence_clauses_per_regulation", "min_queries",
                "planner_tool_calls", "planner_tool_rounds", "dimensions"):
        if type(config[key]) is not int or config[key] < 1:
            parser.error(f"{key} must be a positive integer")
    if config["min_queries"] > config["planner_tool_calls"]:
        parser.error("min_queries exceeds the planner's tool-call budget")
    if any("opus" in config[key].lower() for key in ("model", "verification_model", "planner_model")):
        parser.error("Opus is not used in this experiment")
    if args.dry_run:
        print(f"Database ready: {len(corpus)} clauses in {len(documents)} regulation/version groups.")
        print(f"Planner: {config['planner_model']}; assessment: {config['model']}; verification: {config['verification_model']}")
        print(f"All {len(corpus)} clauses/query; top {config['regulations_per_query']} distinct regulations "
              f"using {config['evidence_clauses_per_regulation']} evidence clauses each; "
              f"at least {config['min_queries']} searches; {config['workers']} workers.")
        print("No API calls or output writes. Actual scan size depends on agent searches.")
        return 0
    pricing = json.loads((HERE / "pricing.json").read_text(encoding="utf-8"))
    for model in (config["model"], config["verification_model"], config["planner_model"]):
        if model not in pricing:
            parser.error(f"Add rates for {model} to pricing.json before running")
    load_dotenv(HERE / ".env")
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        parser.error("Set ANTHROPIC_API_KEY in .env")
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        parser.error("Set GEMINI_API_KEY (or GOOGLE_API_KEY) for query embeddings")
    costs = RunCosts(args.output / "costs.json", pricing)
    costs.data["note"] += " Gemini query embedding charges are additional; see embedding-costs.json."
    write_json(costs.path, costs.data)
    planner_config = dict(config, model=config["planner_model"],
                          max_tool_rounds=config["planner_tool_rounds"], max_tool_calls=config["planner_tool_calls"])
    planner = Claude(planner_config, spec, None, HERE / ".cache/claude", corpus, costs, "planning")
    tools = SearchTools(table, config, HERE / ".cache", args.output, costs, documents)
    write_json(args.output / "embedding-costs.json", tools.usage)
    # Preserve the previous prediction file instead of leaving it looking current
    # if this invocation stops during planning or validation.
    previous = args.output / "predictions.json"
    if previous.exists():
        previous.replace(args.output / "predictions.previous.json")
    catalogue = [{"regulation": d[0]["regulation"], "version": d[0]["version"], "clauses": len(d)} for d in documents]
    print("Planning searches (Claude cost excludes Gemini query embedding charges)...", flush=True)
    try:
        planning = run_batch(plan, (tools, catalogue), planner, "Planning", 1)
    except Exception as error:
        write_json(args.output / "diagnostics.json", {"complete": False, "stage": "planning", "error": str(error),
                   "searches": tools.trace, "attempts": getattr(error, "attempts", [])})
        print(f"Planning failed: {error}", file=sys.stderr)
        return 1
    write_json(args.output / "retrieval.json", {**planning, "selected_regulations": sorted(tools.selected)})
    selected = [d for d in documents if (d[0]["regulation"], d[0]["version"]) in tools.selected]
    selected_count = sum(len(d) for d in selected)
    batches = make_batches(selected, config["batch_size"], config["batch_characters"])
    if args.max_batches:
        batches = batches[:args.max_batches]
    assigned = [c["id"] for batch in batches for c in batch]
    print(f"Retrieved {len(selected)} regulations: {selected_count} clauses; assigning {len(assigned)} in {len(batches)} batches.")
    print(f"Claude cost so far: ${costs.total():.4f}; Gemini charges additional.")
    if args.retrieve_only:
        return 0
    client = Claude(config, spec, None, HERE / ".cache/claude", corpus, costs, "assessment")
    verification_client = Claude(dict(config, model=config["verification_model"]),
                                 spec, None, HERE / ".cache/claude", corpus, costs, "verification")
    diagnostics = {"config": config, "started_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version, "seed": None,
        "coverage": {"available": len(corpus), "retrieved": selected_count, "selected_regulations": sorted(tools.selected), "assigned": len(assigned), "complete": False},
        "batches": [], "candidates": [], "verification": [], "errors": []}
    outcomes = {}
    with tqdm(total=len(batches), desc="Assessment", unit="batch", dynamic_ncols=True) as progress, \
            ThreadPoolExecutor(max_workers=config["workers"]) as pool:
        futures = {pool.submit(run_batch, assess_batch, (b, documents, corpus), client, "Assessment", i + 1):
                   i for i, b in enumerate(batches)}
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
    candidates, jobs = [], []
    for i in sorted(outcomes):
        outcome = outcomes[i]
        diagnostics["batches"].append({"batch": i + 1, "decisions": outcome["decisions"], "history": outcome["history"],
                                      "attempts": outcome["batch_attempts"]})
        group = []
        for decision in outcome["decisions"]:
            for number, requirement in enumerate(decision["requirements"]):
                candidate = dict(requirement, candidate_id=f"{decision['clause_id']}:r{number}",
                                 assessed_clause_id=decision["clause_id"])
                candidates.append(candidate)
                group.append(candidate)
        for start in range(0, len(group), 12):
            jobs.append((group[start:start + 12], outcome["context"]))
    diagnostics["candidates"] = candidates
    supported = set()
    verification_failures = 0
    with tqdm(total=len(jobs), desc="Verification", unit="batch", dynamic_ncols=True) as progress, \
            ThreadPoolExecutor(max_workers=config["workers"]) as pool:
        futures = {pool.submit(run_batch, verify_batch, (group, context, corpus), verification_client, "Verification", i + 1):
                   group for i, (group, context) in enumerate(jobs)}
        for future in as_completed(futures):
            try:
                verified = future.result()
                diagnostics["verification"].append(verified)
                supported.update(r["candidate_id"] for r in verified["results"] if r["status"] == "supported")
            except Exception as error:
                diagnostics["errors"].append({"stage": "verification", "candidate_ids":
                    [c["candidate_id"] for c in futures[future]], "error": str(error),
                    "attempts": getattr(error, "attempts", [])})
                verification_failures += 1
                tqdm.write(f"Verification batch failed: {error}", file=sys.stderr)
            finally:
                progress.set_postfix(supported=len(supported), failed=verification_failures,
                                     cost=f"${costs.total():.4f}", refresh=False)
                progress.update(1)
    accepted = [c for c in candidates if c["candidate_id"] in supported]
    submission, links = submission_for(accepted, corpus, args.team_id, args.case_id)
    diagnostics["submission_ids"] = links
    all_decisions = [d for o in outcomes.values() for d in o["decisions"]]
    diagnostics["coverage"].update({"assessed": len(all_decisions),
        "unassessed_ids": sorted(set(assigned) - {d["clause_id"] for d in all_decisions}),
        "status_counts": dict(Counter(d["status"] for d in all_decisions)),
        "complete": len(all_decisions) == selected_count and not diagnostics["errors"]})
    problems = [str(p) for p in validate(submission, index=index, strict=True)]
    if len((json.dumps(submission, ensure_ascii=False, indent=2) + "\n").encode()) > MAX_BYTES:
        problems.append("Submission exceeds 5 MiB")
    diagnostics["validation_errors"] = problems
    diagnostics["finished_at"] = datetime.now(timezone.utc).isoformat()
    diagnostics["estimated_cost_usd"] = costs.total()
    print(f"Estimated Claude cost this run (Gemini additional): ${costs.total():.4f} USD (see costs.json)")
    write_json(args.output / "diagnostics.json", diagnostics)
    if problems:
        print("Validation failed; predictions.json was not written. See diagnostics.json.", file=sys.stderr)
        return 1
    write_json(args.output / "predictions.json", submission)
    print(f"Wrote predictions.json ({len(accepted)} requirements) and diagnostics.json")
    if diagnostics["errors"]:
        print("Run incomplete: see diagnostics errors; rerun to resume cached successful calls.", file=sys.stderr)
    elif not diagnostics["coverage"]["complete"]:
        print("Partial run: --max-batches left selected clauses unassessed.", file=sys.stderr)
    return int(bool(diagnostics["errors"]) or not diagnostics["coverage"]["complete"])


if __name__ == "__main__":
    sys.exit(main())
