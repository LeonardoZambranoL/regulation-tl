"""Exhaustive concurrent Claude clause assessment; submission + diagnostics."""

import argparse
import base64
import copy
import hashlib
import json
import mimetypes
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
from dotenv import load_dotenv
from tqdm import tqdm

import prompts

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "approaches/benchmarking"))
from challenge_tools.validate import validate, load_index, MAX_BYTES


def obj(**properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def array(items):
    return {"type": "array", "items": items}


STRING = {"type": "string"}
NUMBER = {"type": "number"}
EVIDENCE = obj(source={"enum": ["spec", "image"], "type": "string"}, quote=STRING)
REQUIREMENT = obj(text=STRING, source_id=STRING, page={"type": "integer"},
                  quote=STRING, product_evidence=EVIDENCE, reason=STRING, confidence=NUMBER)
ASSESS_SCHEMA = obj(decisions=array(obj(
    clause_id=STRING, status={"type": "string", "enum": ["relevant", "irrelevant", "needs_context"]},
    reason=STRING, confidence=NUMBER,
    requests=array(obj(regulation=STRING, query=STRING)), requirements=array(REQUIREMENT))))
VERIFY_SCHEMA = obj(results=array(obj(
    candidate_id=STRING, status={"type": "string", "enum": ["supported", "unsupported", "unresolved"]},
    reason=STRING, confidence=NUMBER)))


def normalized(text):
    return " ".join(text.split())


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def check_ids(rows, key, expected):
    ids = [row[key] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError(f"Missing, duplicate, or unexpected {key}; every assigned ID must be returned")
    for row in rows:
        if "confidence" in row and not 0 <= row["confidence"] <= 1:
            raise ValueError("Confidence must be between 0 and 1")


def load_corpus(folder, index):
    allowed = {(r["regulation"], v["version_label"]) for r in index
               for v in r.get("versions", []) if v.get("role") == "base"}
    corpus, documents = {}, []
    for path in sorted(folder.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if (doc["regulation"], doc["version"]) not in allowed:
            raise ValueError(f"{path.name}: not an allowed base regulation/version")
        entries = []
        for number, clause in enumerate(doc["clauses"]):
            if not clause["text"].strip() or not clause["pages"] or any(
                type(page) is not int or page < 1 for page in clause["pages"]
            ):
                raise ValueError(f"{path.name} entry {number}: empty text or invalid pages")
            entry = dict(clause, id=f"{path.stem}:{number}",
                         regulation=doc["regulation"], version=doc["version"])
            corpus[entry["id"]] = entry
            entries.append(entry)
        documents.append(entries)
    if not corpus:
        raise ValueError("No clause records found")
    return corpus, documents


def make_batches(documents, size, characters):
    batches = []
    for entries in documents:
        batch, count = [], 0
        for entry in entries:
            length = len(entry["text"])
            if batch and (len(batch) >= size or count + length > characters):
                batches.append(batch)
                batch, count = [], 0
            batch.append(entry)
            count += length
        if batch:
            batches.append(batch)
    return batches


def context_for(targets, documents, limit):
    """Scope, parent labels and neighbours, with explicit budget omissions."""
    selected = {c["id"] for c in targets}
    wanted = []
    for entries in documents:
        positions = [i for i, c in enumerate(entries) if c["id"] in selected]
        if not positions:
            continue
        labels = set()
        for i in positions:
            label = entries[i].get("paragraph") or ""
            while "." in label:
                label = label.rsplit(".", 1)[0]
                labels.add(label)
            if " / " in label:
                labels.add(label.split(" / ")[0])
        wanted += [c for c in entries if c.get("paragraph") in labels]
        wanted += [c for c in entries if c.get("paragraph") == "1" or
                   (c.get("paragraph") or "").startswith("1.")]
        for i in positions:
            wanted += entries[max(0, i - 2):i] + entries[i + 1:i + 3]
    return bounded_context(wanted, selected, limit)


def bounded_context(entries, excluded, limit):
    result, omitted, used, seen = [], [], 0, set(excluded)
    for entry in entries:
        if entry["id"] in seen:
            continue
        seen.add(entry["id"])
        if used + len(entry["text"]) > limit:
            omitted.append(entry["id"])
            continue
        result.append(entry)
        used += len(entry["text"])
    return result, omitted


TOOL_DEFINITIONS = [
    {"name": "search_clauses", "description": (
        "Search local base regulation clauses by paragraph label or words. "
        "Use regulation='' to search all regulations, offset=0 initially. "
        "Returns up to eight discovery snippets and IDs. Read clauses before citing them."),
     "input_schema": obj(regulation=STRING, query=STRING, offset={"type": "integer"})},
    {"name": "read_clause", "description": (
        "Read a source clause by ID, with citation metadata. Start with offset=0. "
        "If next_offset is not null, call again with that character offset to read more."),
     "input_schema": obj(clause_id=STRING, offset={"type": "integer"})},
]


class ClauseTools:
    def __init__(self, corpus, supplied, limit):
        self.corpus, self.supplied, self.limit = corpus, supplied, limit
        self.trace = []

    def execute(self, name, arguments):
        definitions = {tool["name"]: tool for tool in TOOL_DEFINITIONS}
        try:
            if name not in definitions:
                raise ValueError("Unknown tool")
            jsonschema.validate(arguments, definitions[name]["input_schema"])
            offset = arguments["offset"]
            if type(offset) is not int or offset < 0:
                raise ValueError("offset must be a nonnegative integer")
            if name == "search_clauses":
                query = arguments["query"].strip().lower()
                if not query:
                    raise ValueError("Search query cannot be empty")
                words = set(re.findall(r"\w+", query))
                ranked = []
                for entry in self.corpus.values():
                    if arguments["regulation"] and entry["regulation"].casefold() != arguments["regulation"].casefold():
                        continue
                    label = (entry.get("paragraph") or "").lower()
                    exact = bool(label and (label == query or label.startswith(query + " / ")))
                    score = 1000 * exact + len(words & set(re.findall(r"\w+", entry["text"].lower())))
                    if score:
                        ranked.append((score, entry))
                ranked.sort(key=lambda item: -item[0])
                selected = ranked[offset:offset + 8]
                results = [{"id": c["id"], "regulation": c["regulation"],
                            "paragraph": c.get("paragraph"), "pages": c["pages"],
                            "snippet": c["text"][:400]} for _, c in selected]
                output = {"matches": results, "total_matches": len(ranked),
                          "next_offset": offset + 8 if offset + 8 < len(ranked) else None}
            else:
                entry = self.corpus.get(arguments["clause_id"])
                if entry is None:
                    raise ValueError("Unknown clause ID; use search_clauses to find IDs")
                if offset >= len(entry["text"]):
                    raise ValueError("offset is past the end of this clause")
                text = entry["text"][offset:offset + self.limit]
                output = {k: v for k, v in entry.items() if k != "text"}
                output.update(text=text, offset=offset, total_characters=len(entry["text"]),
                              next_offset=offset + len(text) if offset + len(text) < len(entry["text"]) else None)
                # Only actually read text is eligible supporting evidence. Never
                # silently expose the unread remainder to quote validation.
                if entry["id"] not in self.supplied:
                    self.supplied[entry["id"]] = dict(entry, text=text, evidence_texts=[text])
                elif "evidence_texts" in self.supplied[entry["id"]]:
                    saved = self.supplied[entry["id"]]
                    saved["evidence_texts"] = [*saved["evidence_texts"], text]
                    saved["text"] += "\n[Separate retrieved excerpt]\n" + text
            error = False
        except (ValueError, KeyError, jsonschema.ValidationError) as exc:
            output, error = {"error": str(exc)[:500]}, True
        self.trace.append({"name": name, "input": arguments, "output": output, "is_error": error})
        return output, error


class RunCosts:
    """Thread-safe, per-invocation estimates persisted after every API response."""
    def __init__(self, path, pricing):
        self.path, self.pricing = path, pricing
        self.lock = threading.Lock()
        self.data = {
            "currency": "USD", "scope": "This invocation only; local cache replays cost zero",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "estimated_total_usd": 0.0, "unpriced_requests": 0, "stages": {},
            "note": "Estimate from returned usage and pricing.json, not an invoice. Unpriced requests may add cost.",
        }
        write_json(self.path, self.data)

    def record(self, stage, model, usage=None, cached=False, unknown=False):
        with self.lock:
            row = self.data["stages"].setdefault(stage, {
                "model": model, "api_responses": 0, "local_cache_hits": 0,
                "input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0,
                "cache_read_tokens": 0, "estimated_usd": 0.0,
                "rates_usd_per_million_tokens": self.pricing[model],
            })
            if cached:
                row["local_cache_hits"] += 1
            elif unknown or usage is None:
                self.data["unpriced_requests"] += 1
            else:
                row["api_responses"] += 1
                inputs, outputs = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
                writes, reads = usage.get("cache_creation_input_tokens", 0), usage.get("cache_read_input_tokens", 0)
                hour = usage.get("cache_creation", {}).get("ephemeral_1h_input_tokens", 0)
                rates = self.pricing[model]
                if inputs + writes + reads > rates.get("long_context_threshold", float("inf")):
                    rates = rates["long_context_rates"]
                amount = (inputs * rates["input"] + outputs * rates["output"] +
                          max(0, writes - hour) * rates["cache_write_5m"] +
                          hour * rates["cache_write_1h"] + reads * rates["cache_read"]) / 1_000_000
                row["input_tokens"] += inputs
                row["output_tokens"] += outputs
                row["cache_write_tokens"] += writes
                row["cache_read_tokens"] += reads
                row["estimated_usd"] = round(row["estimated_usd"] + amount, 10)
                self.data["estimated_total_usd"] = round(self.data["estimated_total_usd"] + amount, 10)
            self.data["updated_at"] = datetime.now(timezone.utc).isoformat()
            write_json(self.path, self.data)

    def total(self):
        with self.lock:
            return self.data["estimated_total_usd"]


class Claude:
    def __init__(self, config, spec, image, cache, corpus, costs=None, stage="assessment"):
        self.config, self.spec, self.image, self.cache = config, spec, image, cache
        self.costs, self.stage = costs, stage
        # Tool results depend on the full corpus, not just initial context.
        self.corpus_revision = hashlib.sha256(json.dumps(corpus, sort_keys=True).encode()).hexdigest()

    def request(self, body):
        key = hashlib.sha256(json.dumps({"api_cache": 2, "corpus": self.corpus_revision,
                                        "body": body, **({"batch_retry": self.batch_retry}
                                        if getattr(self, "batch_retry", 0) else {})}, sort_keys=True).encode()).hexdigest()
        path = self.cache / f"{key}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if self.costs:
                self.costs.record(self.stage, self.config["model"], cached=True)
            return data, {"cache_hit": True, "usage": data.get("usage", {})}
        for attempt in range(3):
            try:
                request = urllib.request.Request("https://api.anthropic.com/v1/messages",
                    data=json.dumps(body).encode(), headers={
                        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                        "anthropic-version": "2023-06-01", "content-type": "application/json"})
                with urllib.request.urlopen(request, timeout=240) as response:
                    data = json.load(response)
                if self.costs:
                    self.costs.record(self.stage, self.config["model"], data.get("usage"))
                if data.get("stop_reason") not in ("end_turn", "tool_use"):
                    raise ValueError(f"Incomplete/refused model response: {data.get('stop_reason')}")
                write_json(path, data)
                return data, {"cache_hit": False, "usage": data.get("usage", {})}
            except urllib.error.HTTPError as error:
                if self.costs and error.code >= 500:
                    self.costs.record(self.stage, self.config["model"], unknown=True)
                if error.code not in (429, 500, 502, 503, 504, 529):
                    raise RuntimeError(f"Claude HTTP {error.code}; check API key, model access and request settings") from None
                last = f"Claude HTTP {error.code}"
            except (ValueError, urllib.error.URLError, TimeoutError) as error:
                if self.costs and isinstance(error, (urllib.error.URLError, TimeoutError, json.JSONDecodeError)):
                    self.costs.record(self.stage, self.config["model"], unknown=True)
                last = str(error)[:500]
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError(last)

    def call(self, system, payload, schema, check, tools):
        content = [{"type": "text", "text": json.dumps({"product_spec": self.spec, **payload}, ensure_ascii=False)}]
        if self.image:
            content.append(self.image)
        messages = [{"role": "user", "content": content}]
        turns, calls, corrections, history = 0, 0, 0, []
        while True:
            enabled = turns < self.config["max_tool_rounds"] and calls < self.config["max_tool_calls"]
            body = {"model": self.config["model"], "max_tokens": self.config["max_tokens"],
                    "system": system, "messages": messages, "tools": getattr(tools, "definitions", TOOL_DEFINITIONS),
                    "tool_choice": {"type": "auto" if enabled else "none"},
                    "output_config": {"format": {"type": "json_schema", "schema": schema}}}
            data, usage = self.request(body)
            history.append({"turn": len(history) + 1, "stop_reason": data["stop_reason"], **usage})
            messages.append({"role": "assistant", "content": data["content"]})
            if data["stop_reason"] == "tool_use":
                if not enabled:
                    raise ValueError("Model attempted tools after its tool budget ended")
                results = []
                tool_calls = [block for block in data["content"] if block["type"] == "tool_use"]
                if not tool_calls:
                    raise ValueError("Tool-use response contained no tool calls")
                for block in tool_calls:
                    if calls >= self.config["max_tool_calls"]:
                        output, error = {"error": "Tool budget exhausted; return final decisions with unresolved cases marked."}, True
                        tools.trace.append({"name": block["name"], "input": block["input"],
                                            "output": output, "is_error": True})
                    else:
                        output, error = tools.execute(block["name"], block["input"])
                        calls += 1
                    results.append({"type": "tool_result", "tool_use_id": block["id"],
                                    "content": json.dumps(output, ensure_ascii=False), "is_error": error})
                turns += 1
                if turns >= self.config["max_tool_rounds"] or calls >= self.config["max_tool_calls"]:
                    results.append({"type": "text", "text": "Tool budget exhausted. Return final JSON now; mark insufficient evidence needs_context/unresolved."})
                messages.append({"role": "user", "content": results})
                continue
            try:
                result = json.loads("".join(block["text"] for block in data["content"] if block["type"] == "text"))
                jsonschema.validate(result, schema)
                check(result)
                return result, {"turns": history, "tool_calls": tools.trace,
                                "tool_budget_exhausted": not enabled}
            except (ValueError, jsonschema.ValidationError) as error:
                corrections += 1
                if corrections > 2:
                    raise
                history[-1]["validation_error"] = str(error)[:500]
                messages.append({"role": "user", "content": "Correct your final JSON. Validation failed: " + str(error)[:500]})


def check_assessment(result, targets, supplied, spec, has_image):
    check_ids(result["decisions"], "clause_id", [c["id"] for c in targets])
    for decision in result["decisions"]:
        if decision["status"] != "relevant" and decision["requirements"]:
            raise ValueError("Only relevant decisions can emit requirements")
        for req in decision["requirements"]:
            if req["source_id"] != decision["clause_id"]:
                raise ValueError("Requirement source_id must equal its assigned decision clause_id; other clauses are context only")
            if not 0 <= req["confidence"] <= 1 or not req["text"].strip() or len(req["text"]) > 2000:
                raise ValueError("Invalid requirement text/confidence")
            source = supplied.get(req["source_id"])
            if not source or req["page"] not in source["pages"]:
                raise ValueError("Requirement cites unavailable evidence/page")
            if not req["quote"].strip() or not any(normalized(req["quote"]) in normalized(text)
                for text in source.get("evidence_texts", [source["text"]])):
                raise ValueError("Supporting quote is not present in the cited clause")
            evidence = req["product_evidence"]
            if not evidence["quote"].strip():
                raise ValueError("Missing product evidence")
            if evidence["source"] == "spec" and normalized(evidence["quote"]) not in normalized(spec):
                raise ValueError("Product evidence is not an exact spec quote")
            if evidence["source"] == "image" and not has_image:
                raise ValueError("No image was provided")


def assess_batch(targets, documents, corpus, client):
    context, omitted = context_for(targets, documents, client.config["context_characters"])
    supplied = {c["id"]: dict(c) for c in targets + context}
    tools = ClauseTools(corpus, supplied, client.config["context_characters"])
    result, trace = client.call(prompts.ASSESS,
        {"targets": targets, "context": context, "omitted_context_ids": omitted}, ASSESS_SCHEMA,
        lambda r: check_assessment(r, targets, supplied, client.spec, bool(client.image)), tools)
    return {"decisions": result["decisions"],
            "history": [{"omitted_context_ids": omitted, **trace}],
            "context": list(supplied.values())}


def verify_batch(candidates, context, corpus, client):
    evidence = {c["source_id"]: corpus[c["source_id"]] for c in candidates}
    supplied = {c["id"]: dict(c) for c in context}
    supplied.update(evidence)
    tools = ClauseTools(corpus, supplied, client.config["context_characters"])
    result, trace = client.call(prompts.VERIFY,
        {"candidates": candidates, "evidence": list(evidence.values()), "context": context}, VERIFY_SCHEMA,
        lambda r: check_ids(r["results"], "candidate_id", [c["candidate_id"] for c in candidates]), tools)
    return {"results": result["results"], **trace}


class BatchFailure(RuntimeError):
    def __init__(self, attempts):
        self.attempts = attempts
        super().__init__(f"Failed after {len(attempts)} attempts: {attempts[-1]['error']}")


def run_batch(function, arguments, client, stage, number):
    """Retry the entire agent task after its internal API/validation retries fail."""
    attempts = []
    for retry in range(client.config.get("batch_retries", 2) + 1):
        worker_client = copy.copy(client)
        worker_client.batch_retry = retry
        try:
            result = function(*arguments, worker_client)
            attempts.append({"attempt": retry + 1, "status": "ok"})
            result["batch_attempts"] = attempts
            return result
        except Exception as error:
            attempts.append({"attempt": retry + 1, "status": "failed", "error": str(error)})
            if retry < client.config.get("batch_retries", 2):
                delay = min(2 ** (retry + 1), 30)
                tqdm.write(f"{stage} batch {number}: attempt {retry + 1} failed; retrying in {delay}s: {error}", file=sys.stderr)
                time.sleep(delay)
    raise BatchFailure(attempts)


def submission_for(candidates, corpus, team_id, case_id):
    requirements, links = [], {}
    for i, candidate in enumerate(candidates, 1):
        clause = corpus[candidate["source_id"]]
        source = {"regulation": clause["regulation"], "version": clause["version"], "page": candidate["page"]}
        if clause.get("paragraph"):
            source["paragraph"] = clause["paragraph"]
        rid = f"R-{i:04d}"
        requirements.append({"id": rid, "text": candidate["text"], "source": source})
        links[candidate["candidate_id"]] = rid
    return {"team_id": team_id, "case_id": case_id, "requirements": requirements}, links

