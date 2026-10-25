"""Cached ingestion, reviewable regulation diff, and tool-driven change drafting."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ingest_versions(root: Path, case: str, old_pdf: Path, new_pdf: Path, *, regulation: str = "UN R175", old_version: str = "0.1.0", new_version: str = "1.0.0", output_dir: Path | None = None) -> dict[str, Any]:
    """Reuse shared old text/clauses and run the shared ingestion scripts once for a new PDF hash."""
    repo = root.parents[2]
    stem = regulation.replace(" ", "_")
    output_dir = output_dir or root / "outputs"
    shared_text = repo / "data-ingestion" / "text" / f"{stem}_base.txt"
    shared_clauses = repo / "data-ingestion" / "clauses" / f"{stem}_base.json"
    if not shared_text.is_file() or not shared_clauses.is_file():
        raise FileNotFoundError(f"Shared {regulation} base text/clauses are missing; run data-ingestion first.")
    old_txt = shared_text.read_text(encoding="utf-8")
    old_doc = json.loads(shared_clauses.read_text(encoding="utf-8"))
    if old_doc.get("regulation") != regulation or old_doc.get("version") != old_version:
        raise ValueError("Shared base clauses do not match configured regulation/version")
    digest = _sha(new_pdf)
    case_manifest = Path(os.environ.get("INDUSTRIAL_AI_HACKATHON", repo.parent / "industrial-ai-hackathon")) / "subgoal" / case / "files.json"
    if case_manifest.is_file():
        listed = {entry["name"]:entry["sha256"] for entry in json.loads(case_manifest.read_text(encoding="utf-8"))}
        if listed.get("old.pdf") and _sha(old_pdf) != listed["old.pdf"]:
            raise ValueError("Old PDF checksum does not match the supplied case manifest.")
        if listed.get("new.pdf") and digest != listed["new.pdf"]:
            raise ValueError("New PDF checksum does not match the supplied case manifest.")
    cache = root / ".cache" / "ingestion" / digest
    txt = cache / "text" / "new.txt"
    clause_json = cache / "clauses" / "new.json"
    manifest = cache / "manifest.json"
    if not (txt.is_file() and clause_json.is_file() and manifest.is_file()):
        cache.mkdir(parents=True, exist_ok=True)
        input_dir = cache / "pdf"
        input_dir.mkdir(parents=True, exist_ok=True)
        stable_pdf = input_dir / f"{stem}_latest.pdf"
        if not stable_pdf.exists() or _sha(stable_pdf) != digest:
            import shutil
            shutil.copy2(new_pdf, stable_pdf)
        text_dir, clause_dir = cache / "text", cache / "clauses"
        commands = [
            [sys.executable, str(repo / "data-ingestion" / "pdf_to_txt.py"), "--input", str(input_dir), "--output", str(text_dir)],
            [sys.executable, str(repo / "data-ingestion" / "txt_to_clauses.py"), "--input", str(text_dir), "--output", str(clause_dir)],
        ]
        for command in commands:
            subprocess.run(command, cwd=repo, check=True, capture_output=True, text=True)
        produced_txt = text_dir / f"{stem}_latest.txt"
        produced_json = clause_dir / f"{stem}_latest.json"
        if not produced_txt.is_file() or not produced_json.is_file():
            raise RuntimeError(f"Shared ingestion scripts completed without expected {regulation} outputs.")
        produced_txt.replace(txt)
        produced_json.replace(clause_json)
        manifest.write_text(json.dumps({"pdf_sha256": digest, "parser": "data-ingestion/pdf_to_txt.py + txt_to_clauses.py"}, indent=2), encoding="utf-8")
    new_txt = txt.read_text(encoding="utf-8")
    new_doc = json.loads(clause_json.read_text(encoding="utf-8"))
    old_pages = {int(m.group(1)) for m in re.finditer(r"^=== PDF PAGE (\d+) ===$", old_txt, re.M)}
    new_pages = {int(m.group(1)) for m in re.finditer(r"^=== PDF PAGE (\d+) ===$", new_txt, re.M)}
    diff = "\n".join(difflib.unified_diff(
        old_txt.splitlines(), new_txt.splitlines(), fromfile=f"{regulation} {old_version}", tofile=f"{regulation} {new_version}", lineterm="", n=4,
    ))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"diff-{case}.patch").write_text(diff + "\n", encoding="utf-8")
    return {"old_text": old_txt, "new_text": new_txt, "old_doc": old_doc, "new_doc": new_doc,
            "diff": diff, "new_sha256": digest, "old_pages": len(old_pages), "new_pages": len(new_pages)}


def as_alignment_doc(doc: dict, digest: str = "") -> dict:
    provisions=[]
    for i,c in enumerate(doc.get("clauses", [])):
        para=str(c.get("paragraph") or "preamble")
        pages=c.get("pages") or [1]
        provisions.append({"key":f"main|{para}","container":"main","paragraph":para,"page":int(pages[0]),
                           "pages":pages,"parent":None,"depth":para.count(".")+1,"text":c.get("text", ""),
                           "title":"","is_heading":False,"tables":[],"index":i})
    return {"source":"shared data-ingestion clauses","sha256":digest,"page_count":max((p["page"] for p in provisions),default=0),
            "pages":[],"provisions":provisions}


TOOLS = [
    {"name":"search_regulation", "description":"Search exact source text in one regulation version. Returns matching lines with page marker and nearby text.", "input_schema":{"type":"object","properties":{"version":{"type":"string","enum":["old","new"]},"query":{"type":"string"},"regex":{"type":"boolean"},"limit":{"type":"integer","minimum":1,"maximum":30}},"required":["version","query"],"additionalProperties":False}},
    {"name":"get_clause", "description":"Read a parsed clause by exact or partial paragraph label in one version, including pages and full text.", "input_schema":{"type":"object","properties":{"version":{"type":"string","enum":["old","new"]},"paragraph":{"type":"string"}},"required":["version","paragraph"],"additionalProperties":False}},
    {"name":"read_page", "description":"Read full extracted page text from the source .txt using its PDF page marker.", "input_schema":{"type":"object","properties":{"version":{"type":"string","enum":["old","new"]},"page":{"type":"integer","minimum":1}},"required":["version","page"],"additionalProperties":False}},
    {"name":"list_requirements", "description":"Find existing requirements by ID/text/source paragraph. Empty query returns all IDs and short text excerpts; limit 100 lists the full dev set.", "input_schema":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":100}},"required":["query"],"additionalProperties":False}},
    {"name":"get_requirement", "description":"Read the complete existing engineering requirement and its source citation by ID.", "input_schema":{"type":"object","properties":{"requirement_id":{"type":"string"}},"required":["requirement_id"],"additionalProperties":False}},
    {"name":"stage_change", "description":"Stage one schema-valid change. Modified and removed require an existing ID; added must have null ID. Modified/added new_text must be 1-2000 characters and cite the new version. For removed, omit source or set it to null; it will be omitted from final JSON.", "input_schema":{"type":"object","properties":{"requirement_id":{"type":["string","null"]},"change":{"type":"string","enum":["modified","removed","added"]},"new_text":{"type":["string","null"],"maxLength":2000},"reason":{"type":"string","minLength":1},"source":{"type":["object","null"],"properties":{"page":{"type":"integer","minimum":1},"paragraph":{"type":"string"}},"required":["page"],"additionalProperties":False}},"required":["requirement_id","change","new_text","reason","source"],"additionalProperties":False}},
    {"name":"finish_review", "description":"Finish after reviewing all changed regions and existing requirements implicated by the diff.", "input_schema":{"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"],"additionalProperties":False}},
]


def _page_text(text: str, number: int) -> str:
    pages = re.split(r"(?m)^=== PDF PAGE (\d+) ===\s*$", text)
    for i in range(1, len(pages), 2):
        if int(pages[i]) == number:
            return pages[i + 1].strip()[:12000]
    return "No page with that marker."


def run_tool(name: str, args: dict, state: dict) -> str:
    if name == "search_regulation":
        src = state[args["version"] + "_text"]
        query = args["query"]
        try:
            matcher = re.compile(query, re.I) if args.get("regex") else re.compile(re.escape(query), re.I)
        except re.error as exc:
            return f"Invalid search expression: {exc}"
        lines = src.splitlines()
        hit_ids = [i for i, line in enumerate(lines) if matcher.search(line)]
        limit = args.get("limit", 12)
        hits = []
        used = set()
        for i in hit_ids[:limit]:
            lo, hi = max(0, i - 2), min(len(lines), i + 3)
            if any(j in used for j in range(lo, hi)):
                continue
            used.update(range(lo, hi))
            hits.append("\n".join(f"{j+1}: {lines[j]}" for j in range(lo, hi)))
        return "\n---\n".join(hits) if hits else "No matches."
    if name == "get_clause":
        query = args["paragraph"].casefold()
        rows = [c for c in state[args["version"] + "_clauses"] if query in str(c.get("paragraph", "")).casefold()]
        return json.dumps(rows[:8], ensure_ascii=False) if rows else "No clause label matched."
    if name == "read_page":
        return _page_text(state[args["version"] + "_text"], args["page"])
    if name == "list_requirements":
        query = args["query"].casefold()
        rows = [r for r in state["requirements"] if not query or query in json.dumps(r, ensure_ascii=False).casefold()]
        return json.dumps([{"id":r["id"],"text":r.get("text","")[:260],"source":r.get("source")} for r in rows[:args.get("limit",100)]], ensure_ascii=False)
    if name == "get_requirement":
        return json.dumps(state["req_by_id"].get(args["requirement_id"], {"error":"unknown requirement ID"}), ensure_ascii=False)
    if name == "stage_change":
        row = args.copy()
        rid, kind = row.get("requirement_id"), row["change"]
        if kind in ("modified", "removed") and rid not in state["req_by_id"]:
            return "Rejected: requirement_id must identify an existing requirement."
        if kind == "added" and rid is not None:
            return "Rejected: added requirements must use requirement_id=null."
        if kind in ("added", "modified"):
            if not row.get("new_text") or not row.get("source"):
                return "Rejected: added/modified changes need new_text and a source citation."
            if len(row["new_text"]) > 2000:
                pending=f"{rid or 'added:' + str(row.get('source',{}).get('paragraph','unknown'))}"
                state.setdefault("pending_fixes",[])
                if pending not in state["pending_fixes"]: state["pending_fixes"].append(pending)
                return "Rejected: new_text exceeds the official 2000-character maximum. Condense it faithfully, preserving the changed obligation and its material conditions, then stage again."
            if not 1 <= int(row["source"]["page"]) <= state["new_page_count"]:
                return "Rejected: source page is outside the new PDF."
            para = row["source"].get("paragraph")
            if para and not any(para.casefold() in str(c.get("paragraph", "")).casefold() for c in state["new_clauses"]):
                return "Rejected: cited paragraph was not found in the new parsed clauses."
        if kind in ("modified", "removed"):
            existing = state["staged_by_id"].get(rid)
            if existing == row:
                return "This identical change is already staged."
            state["staged_by_id"][rid] = row
        else:
            norm=lambda s: re.sub(r"\s+"," ",s).strip().casefold()
            para=row.get("source",{}).get("paragraph")
            if any(norm(item.get("new_text",""))==norm(row.get("new_text","")) and item.get("source",{}).get("paragraph")==para for item in state["staged_added"]):
                return "Rejected: duplicate added obligation already staged at this paragraph."
            state["staged_added"].append(row)
        pending=f"{rid or 'added:' + str(row.get('source',{}).get('paragraph','unknown'))}"
        state.setdefault("pending_fixes",[])
        if pending in state["pending_fixes"]: state["pending_fixes"].remove(pending)
        return "Accepted and staged."
    if name == "finish_review":
        if state.get("pending_fixes"):
            return "Cannot finish yet. These previously rejected entries still need valid replacements: " + ", ".join(state["pending_fixes"])
        state["finished"] = True
        state["summary"] = args["summary"]
        return "Review finished."
    return "Unknown tool."


def smoke_test(candidate: dict, model: str, usage_log: Path) -> dict:
    """One small structured LLM call against a real candidate before the agent run."""
    from retrieval import llm
    schema={"type":"object","properties":{"candidate_id":{"type":"string"},"decision":{"type":"string","enum":["unchanged","modified","removed"]},
            "reason":{"type":"string"},"source_page":{"type":["integer","null"]}},"required":["candidate_id","decision","reason","source_page"],"additionalProperties":False}
    prompt=("Smoke-check this single candidate. Determine whether the engineering obligation is unchanged, modified, or removed. "
            "Use the supplied regulation evidence only; return a concise reason and an evidenced new page when applicable.\n"+
            json.dumps(candidate,ensure_ascii=False,separators=(",",":")))
    usage_log.parent.mkdir(parents=True,exist_ok=True)
    totals={"input_tokens":0,"output_tokens":0,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}
    def collect(value):
        for k in totals: totals[k]+=int(value.get(k,0) or 0)
        usd=(totals["input_tokens"]*2+totals["output_tokens"]*10+totals["cache_read_input_tokens"]*.10+totals["cache_creation_input_tokens"]*2.5)/1_000_000
        with usage_log.open("a",encoding="utf-8") as f: f.write(json.dumps({"phase":"smoke",**value})+"\n")
        print(f"[smoke] {value.get('model',model)} input {value.get('input_tokens',0):,}, output {value.get('output_tokens',0):,} | spent ${usd:.4f}",flush=True)
    llm.load_env()
    llm.USAGE_CALLBACK=collect
    try:
        result=llm.structured(prompt,schema,model=model,effort="low",max_tokens=600)
    finally:
        llm.USAGE_CALLBACK=None
    if result.get("candidate_id")!=candidate["candidate_id"] or result.get("decision") not in {"unchanged","modified","removed"} or not result.get("reason"):
        raise ValueError("Smoke test returned malformed or mismatched structured output.")
    cost=(totals["input_tokens"]*2+totals["output_tokens"]*10+totals["cache_read_input_tokens"]*.10+totals["cache_creation_input_tokens"]*2.5)/1_000_000
    return result,{"tokens":totals,"estimated_cost_usd":round(cost,6)}


def analyze(state: dict, model: str, usage_log: Path, checkpoint: Path, max_turns: int = 80) -> tuple[list[dict], dict]:
    import anthropic
    from retrieval import llm
    llm.load_env()
    client = anthropic.Anthropic()
    system = """You analyze regulatory version changes and update engineering requirements. Use the tools, not guesswork. First inspect the unified diff, inventory existing requirements with list_requirements, then search/read enough old and new source context and the implicated requirements. Investigate changed definitions, tables, annexes, cross-references and moved/renumbered text. Report only actual engineering obligation changes, not editorial changes. Preserve an existing requirement ID when modified or removed. Use added with null ID only for genuinely new distinct obligations. Split a provision into separate added entries when it contains distinct engineering obligations. A modified entry must preserve one obligation and state its updated form. Give concise reasons explaining the substantive effect. Cite a real new-version page and paragraph for every modified/added item. Validate your own citations with tools. Stage every entry through stage_change, avoid duplicate obligations, and call finish_review only when done. The initial user message contains the complete unified diff and task."""
    checkpoint.parent.mkdir(parents=True,exist_ok=True)
    saved=json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.is_file() else {}
    old_staged=saved.get("staged_by_id",{})
    staged_by_id={}
    for rid,row in old_staged.items():
        kind=row.get("change")
        valid=(rid in state["req_by_id"] and kind in ("modified","removed") and bool(row.get("reason")))
        if kind=="modified":
            src=row.get("source") or {}
            valid=valid and isinstance(row.get("new_text"),str) and 0<len(row["new_text"])<=2000
            valid=valid and isinstance(src,dict) and 1<=int(src.get("page",0) or 0)<=state["new_page_count"]
        if kind=="removed":
            row.pop("source",None)
        if valid:
            staged_by_id[rid]=row
    staged_added=[]
    for row in saved.get("staged_added",[]):
        src=row.get("source") or {}
        valid=(row.get("requirement_id") is None and row.get("change")=="added" and bool(row.get("reason"))
               and isinstance(row.get("new_text"),str) and 0<len(row["new_text"])<=2000
               and isinstance(src,dict) and 1<=int(src.get("page",0) or 0)<=state["new_page_count"])
        if valid:
            staged_added.append(row)
    invalid_saved=(len(staged_by_id)!=len(old_staged) or len(staged_added)!=len(saved.get("staged_added",[])))
    staged = {"staged_by_id":staged_by_id,"staged_added":staged_added,"finished":saved.get("finished",False) and not invalid_saved}
    state.update(staged)
    state["pending_fixes"]=[]
    if invalid_saved:
        # Discard malformed checkpoint rows and let the model review those cases again.
        checkpoint.write_text(json.dumps({"staged_by_id":staged_by_id,"staged_added":staged_added,"finished":False,
                                          "summary":"Invalid checkpoint rows removed; review resumed."},ensure_ascii=False,indent=2),encoding="utf-8")
    if state["finished"]:
        changes=list(state["staged_by_id"].values())+state["staged_added"]
        return changes,{"api_calls":0,"tokens":{},"elapsed_seconds":0,"estimated_cost_usd":0,"review_summary":saved.get("summary", "resumed completed checkpoint")}
    prior=json.dumps({"by_id":state["staged_by_id"],"added":state["staged_added"]},ensure_ascii=False)
    msg = [{"role":"user","content":f"Analyze changes between {state['regulation']} {state['old_version']} and {state['new_version']}. The full source files and requirements are available through tools. Here is the unified diff:\n```diff\n{state['diff']}\n```\nUse the tools to explore focused context and produce the complete change set. Previously staged entries (do not duplicate; verify and revise if needed): {prior}"}]
    usage_total = {"input_tokens":0,"output_tokens":0,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}
    calls, start = 0, time.monotonic()
    log = usage_log.open("a",encoding="utf-8")
    try:
        for turn in range(max_turns):
            response = client.messages.create(model=model, max_tokens=6000, system=system, tools=TOOLS, messages=msg)
            calls += 1
            u=response.usage
            record={"model":response.model,"input_tokens":u.input_tokens,"output_tokens":u.output_tokens,
                    "cache_read_input_tokens":getattr(u,"cache_read_input_tokens",0),"cache_creation_input_tokens":getattr(u,"cache_creation_input_tokens",0)}
            for k in usage_total: usage_total[k]+=int(record[k] or 0)
            log.write(json.dumps({"call":calls,**record})+"\n"); log.flush()
            usd=(usage_total["input_tokens"]*2+usage_total["output_tokens"]*10+usage_total["cache_read_input_tokens"]*.10+usage_total["cache_creation_input_tokens"]*2.5)/1_000_000
            print(f"[API {calls}] {response.model} | input {record['input_tokens']:,}, output {record['output_tokens']:,} | spent so far ${usd:.4f}",flush=True)
            msg.append({"role":"assistant","content":response.content})
            calls_in_turn=[block for block in response.content if block.type=="tool_use"]
            if not calls_in_turn:
                if state["finished"]: break
                msg.append({"role":"user","content":"Continue reviewing with the tools; call finish_review only when the change analysis is complete."})
                continue
            results=[]
            for call in calls_in_turn:
                result=run_tool(call.name,call.input,state)
                results.append({"type":"tool_result","tool_use_id":call.id,"content":result})
            msg.append({"role":"user","content":results})
            checkpoint.write_text(json.dumps({"staged_by_id":state["staged_by_id"],"staged_added":state["staged_added"],
                                              "finished":state["finished"],"summary":state.get("summary","")},ensure_ascii=False,indent=2),encoding="utf-8")
            if state["finished"]: break
        else:
            raise RuntimeError(f"Tool agent did not finish within {max_turns} turns")
    finally:
        log.close()
    changes=list(state["staged_by_id"].values())+state["staged_added"]
    for row in changes:
        if row.get("source") is None:
            row.pop("source",None)
    return changes,{"api_calls":calls,"tokens":usage_total,"elapsed_seconds":round(time.monotonic()-start,2),"estimated_cost_usd":round(usd,6),"review_summary":state.get("summary","")}
