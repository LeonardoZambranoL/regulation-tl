"""Gold-blind inference stages for contextual clause selection.

The module intentionally imports the existing toolkit writer and ranker instead
of copying or modifying their prompts.
"""

from __future__ import annotations

import hashlib
import base64
import json
import mimetypes
import re
import tempfile
import threading
from datetime import datetime, timezone
from math import ceil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from retrieval.classify import SHALL, candidates
from retrieval.corpus import Chunk, load_corpus
from retrieval.llm import load_env, set_usage_observer
from retrieval.refine import dedupe, refine_ranked
from retrieval.refine import RANK as REUSED_RANK_PROMPT
from retrieval.write import write
from retrieval.write import PROMPTS as REUSED_WRITER_PROMPTS

DECISIONS = ("APPLICABLE", "NOT_APPLICABLE", "CONDITIONAL", "UNCERTAIN")

# Generic normative forms.  This branch is deliberately exhaustive inside the
# fixed regulation set; it is not a semantic top-k and never sees answer keys.
NORMATIVE = re.compile(
    r"\b(shall\s+not|must\s+not|is\s+(?:not\s+)?(?:required|permitted|prohibited)|"
    r"are\s+(?:not\s+)?(?:required|permitted|prohibited)|shall\s+be\s+capable|"
    r"may\s+only|not\s+(?:less|more)\s+than|at\s+(?:least|most)|minimum|maximum|"
    r"tolerance|limit(?:ing)?\s+value|acceptance\s+criteria|pass(?:ed|es)?\s+if)\b",
    re.IGNORECASE,
)
QUANTITATIVE = re.compile(
    r"(?:[<>≤≥]=?\s*\d|\b\d+(?:[.,]\d+)?\s*(?:mm|cm|m|km/h|ms|s|V|A|W|cd|lx|Hz|kHz|MHz|"
    r"nm|°|degrees?|%|N|kN|dB|g|kg|h)\b|\b(?:between|from)\s+\d.+?\b(?:and|to)\s+\d)", re.IGNORECASE
)
TABLEISH = re.compile(r"(?:\|.+\||\b(?:category|class|number|colour|color|height|angle|value)\s*:\s*\S)", re.IGNORECASE)
REFERENCE = re.compile(
    r"\b(?:paragraphs?|paras?\.?|sections?)\s+((?:\d+\.)*\d+)|\b(Annex\s+\d+[A-Z]?(?:\s+(?:Part\s+)?\w+)*)",
    re.IGNORECASE,
)
DEFINITION = re.compile(r"\b(?:means|is defined as|definition of)\b", re.IGNORECASE)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        stream.write(text)
        temp = Path(stream.name)
    temp.replace(path)


def _paragraph_parts(paragraph: str | None) -> list[str]:
    if not paragraph:
        return []
    # Numeric hierarchy works for ordinary paragraphs; Annex labels are kept as
    # space-delimited structural prefixes by the shared corpus loader.
    if paragraph.lower().startswith("annex "):
        bits = paragraph.split()
        return [" ".join(bits[:i]) for i in range(2, len(bits) + 1)]
    bits = paragraph.rstrip(".").split(".")
    return [".".join(bits[:i]) for i in range(1, len(bits) + 1)]


def _compact_chunk(chunk: Chunk, limit: int | None = 2200) -> dict:
    return {
        "regulation": chunk.regulation,
        "version": chunk.version,
        "paragraph": chunk.paragraph,
        "pages": chunk.meta.get("pages", [chunk.page]),
        "text": chunk.text if limit is None else " ".join(chunk.text.split())[:limit],
        "clause_id": chunk.meta.get("clause_id"),
    }


@dataclass
class ContextRecord:
    target: dict
    parents_and_headings: list[dict]
    governing_scope: list[dict]
    relevant_definitions: list[dict]
    referenced_clauses: list[dict]
    applicable_exceptions_and_conditions: list[dict]
    nearby_clauses: list[dict]
    unresolved_references: list[str]


class ContextBuilder:
    def __init__(self, chunks: list[Chunk], cfg: dict):
        self.cfg = cfg
        self.by_reg: dict[str, list[Chunk]] = {}
        self.by_para: dict[tuple[str, str], Chunk] = {}
        for chunk in chunks:
            self.by_reg.setdefault(chunk.regulation, []).append(chunk)
            if chunk.paragraph:
                self.by_para[(chunk.regulation, self._norm_para(chunk.paragraph))] = chunk
        self.position = {c.id: i for reg in self.by_reg.values() for i, c in enumerate(reg)}

    @staticmethod
    def _norm_para(value: str) -> str:
        return re.sub(r"[\s,]+", " ", value.strip().rstrip(".").lower())

    def _resolve(self, target: Chunk) -> tuple[list[Chunk], list[str]]:
        found, missing, seen = [], [], set()
        if not self.cfg.get("resolve_cross_references", True):
            return found, missing
        for match in REFERENCE.finditer(target.text):
            label = next(x for x in match.groups() if x)
            key = self._norm_para(label)
            if key in seen:
                continue
            seen.add(key)
            resolved = self.by_para.get((target.regulation, key))
            if resolved:
                found.append(resolved)
            else:
                missing.append(label)
            if len(found) + len(missing) >= self.cfg.get("max_references", 8):
                break
        return found, missing

    def build(self, target: Chunk) -> ContextRecord:
        reg = self.by_reg[target.regulation]
        ancestors = _paragraph_parts(target.paragraph)[:-1]
        parents = []
        for label in reversed(ancestors):
            parent = self.by_para.get((target.regulation, self._norm_para(label)))
            if parent and parent.id != target.id:
                parents.append(parent)
            if len(parents) >= self.cfg.get("ancestor_depth", 3):
                break
        scope = [c for c in reg if c.paragraph and re.fullmatch(r"1(?:\.\d+)*", c.paragraph.rstrip("."))][:6]
        terms = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]{4,}", target.text)}
        definitions = []
        for c in reg:
            para = (c.paragraph or "").rstrip(".")
            if (para == "2" or para.startswith("2.")) and DEFINITION.search(c.text):
                words = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]{4,}", c.text)}
                if terms & words:
                    definitions.append(c)
            if len(definitions) >= 5:
                break
        refs, missing = self._resolve(target)
        pos = self.position[target.id]
        before, after = self.cfg.get("nearby_before", 1), self.cfg.get("nearby_after", 1)
        nearby = [c for c in reg[max(0, pos - before):pos + after + 1] if c.id != target.id]
        condition_rx = re.compile(r"\b(?:except|unless|provided that|only if|does not apply|exempt|condition)\b", re.I)
        prefix = (_paragraph_parts(target.paragraph)[-2] if len(_paragraph_parts(target.paragraph)) > 1 else None)
        exceptions = [c for c in reg if c.id != target.id and condition_rx.search(c.text) and
                      (c in nearby or (prefix and ((c.paragraph or "") == prefix or
                                                   (c.paragraph or "").startswith(prefix + "."))))][:5]
        record = ContextRecord(
            target=_compact_chunk(target, None),
            parents_and_headings=[_compact_chunk(c, 900) for c in parents],
            governing_scope=[_compact_chunk(c, 900) for c in scope],
            relevant_definitions=[_compact_chunk(c, 900) for c in definitions],
            referenced_clauses=[_compact_chunk(c, 1500) for c in refs],
            applicable_exceptions_and_conditions=[_compact_chunk(c, 1200) for c in exceptions],
            nearby_clauses=[_compact_chunk(c, 900) for c in nearby],
            unresolved_references=missing,
        )
        # Deterministic size cap: optional context is removed before the exact target.
        cap = self.cfg.get("max_context_chars", 12000)
        for field in ("nearby_clauses", "applicable_exceptions_and_conditions", "relevant_definitions",
                      "governing_scope", "parents_and_headings"):
            values = getattr(record, field)
            while values and len(canonical_json(asdict(record))) > cap:
                values.pop()
        return record


PRODUCT_PROMPT = """Extract a structured product model from the supplied specification. Every fact must quote exact
evidence from the input and name a source location such as a heading, bullet, table row, or image caption. Preserve
unknowns explicitly. Never infer that a component, function, material, category, sensor, or feature is absent merely
because it is not mentioned. If an exploded-view image is represented in the markdown, use only its caption/alt text
and other machine-readable evidence; do not pretend to have inspected unavailable pixels.

Return product_and_assembly_type, vehicle_categories, components, functions, materials_and_properties,
electronic_components_and_sensors, explicit_inclusions, explicit_exclusions, and unknown_or_unspecified as lists of
evidence-backed facts.

<spec>\n{spec}\n</spec>"""

CLASSIFY_PROMPT = """You are a UNECE type-approval engineer deciding contextual applicability. Use only the product
model and regulatory context supplied. For every item return exactly one decision:
- APPLICABLE: it imposes a relevant obligation on this product.
- NOT_APPLICABLE: it clearly does not apply; cite exact evidence proving why.
- CONDITIONAL: it imposes an obligation if a condition may be satisfied; retain that condition.
- UNCERTAIN: information or resolved regulatory context is insufficient.

Distinguish the actual component from the host vehicle or another component; general obligations governing an
applicable component; approval, test, installation, marking, and conformity duties; category/technical exclusions;
and explanatory or administrative text with no engineering obligation. Do not treat silence in the specification as
evidence of absence. Do not automatically reject conditional requirements. Never invent unresolved reference text.
Set contains_obligations only when the target or an obligation inherited by its explicit reference imposes something.
Quote exact product and regulatory evidence. Decide every context_id.

<product_model>\n{product}\n</product_model>\n<contexts>\n{contexts}\n</contexts>"""


PRODUCT_SCHEMA = {
    "type": "object",
    "properties": {name: {"type": "array", "items": {"type": "object", "properties": {
        "fact": {"type": "string"}, "evidence": {"type": "string"}, "location": {"type": "string"}},
        "required": ["fact", "evidence", "location"], "additionalProperties": False}}
        for name in ("product_and_assembly_type", "vehicle_categories", "components", "functions",
                     "materials_and_properties", "electronic_components_and_sensors", "explicit_inclusions",
                     "explicit_exclusions", "unknown_or_unspecified")},
    "required": ["product_and_assembly_type", "vehicle_categories", "components", "functions",
                 "materials_and_properties", "electronic_components_and_sensors", "explicit_inclusions",
                 "explicit_exclusions", "unknown_or_unspecified"],
    "additionalProperties": False,
}

DECISION_SCHEMA = {
    "type": "object", "properties": {"decisions": {"type": "array", "items": {
        "type": "object", "properties": {
            "context_id": {"type": "integer"}, "paragraph": {"type": "string"},
            "applicability": {"type": "string", "enum": list(DECISIONS)}, "reason": {"type": "string"},
            "product_evidence": {"type": "string"}, "regulatory_evidence": {"type": "string"},
            "conditions": {"type": "array", "items": {"type": "string"}},
            "referenced_paragraphs": {"type": "array", "items": {"type": "string"}},
            "contains_obligations": {"type": "boolean"}},
        "required": ["context_id", "paragraph", "applicability", "reason", "product_evidence",
                     "regulatory_evidence", "conditions", "referenced_paragraphs", "contains_obligations"],
        "additionalProperties": False}}}, "required": ["decisions"], "additionalProperties": False,
}


class CachedLLM:
    def __init__(self, cache_dir: Path, models: dict[str, str], progress=None):
        self.cache_dir, self.models = cache_dir, models
        self.progress = progress
        self.events: list[dict] = []

    def call(self, stage: str, prompt: str | list[dict], schema: dict, effort: str) -> dict:
        model = self.models[stage]
        key = sha256_text(canonical_json({"model": model, "effort": effort, "prompt": prompt, "schema": schema}))
        path = self.cache_dir / stage / f"{key}.json"
        if path.is_file():
            envelope = json.loads(path.read_text(encoding="utf-8"))
            self.events.append({"stage": stage, "cache_hit": True, "key": key, "usage": envelope.get("usage")})
            if self.progress:
                self.progress.complete_batch(stage, cached=True)
            return envelope["response"]
        import anthropic

        load_env()
        response = anthropic.Anthropic().beta.messages.create(
            model=model, max_tokens=16000,
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(next(block.text for block in response.content if block.type == "text"))
        usage = {name: getattr(response.usage, name, None) for name in
                 ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
        atomic_write_json(path, {"request": {"model": model, "effort": effort,
                                                   "prompt_sha256": sha256_text(canonical_json(prompt)),
                                                   "schema_sha256": sha256_text(canonical_json(schema))},
                                 "usage": usage, "response": data})
        self.events.append({"stage": stage, "cache_hit": False, "key": key, "usage": usage})
        if self.progress:
            self.progress.record_usage(stage, getattr(response, "model", model), usage)
            self.progress.complete_batch(stage, cached=False)
        return data


class LiveProgressCosts:
    """Thread-safe live bars plus a durable per-invocation cost estimate."""

    def __init__(self, path: Path, pricing: dict):
        self.path, self.pricing = path, pricing
        self.lock = threading.Lock()
        self.bar = None
        self.current_stage = None
        self.data = {
            "currency": "USD", "scope": "this variant's inference; local cache hits cost zero; evaluation judge excluded",
            "started_at": datetime.now(timezone.utc).isoformat(), "estimated_total_usd": 0.0,
            "pricing": pricing, "stages": {},
            "note": "Estimate from API token usage and configured public list prices; not an invoice.",
        }
        atomic_write_json(self.path, self.data)

    def start(self, stage: str, total: int, model: str) -> None:
        from tqdm import tqdm
        with self.lock:
            if self.bar is not None:
                self.bar.close()
            self.current_stage = stage
            self._row(stage, model)
            self.bar = tqdm(total=total, desc=stage.replace("_", " ").title(), unit="batch", dynamic_ncols=True)
            self._postfix()

    def _row(self, stage: str, model: str | None = None) -> dict:
        row = self.data["stages"].setdefault(stage, {
            "model": model, "api_responses": 0, "local_cache_hits": 0,
            "input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0,
            "cache_read_tokens": 0, "estimated_usd": 0.0,
        })
        if model:
            row["model"] = model
        return row

    def record_usage(self, stage: str, model: str, usage: dict) -> None:
        with self.lock:
            row = self._row(stage, model)
            inputs = usage.get("input_tokens", 0) or 0
            outputs = usage.get("output_tokens", 0) or 0
            writes = usage.get("cache_creation_input_tokens", 0) or 0
            reads = usage.get("cache_read_input_tokens", 0) or 0
            amount = (inputs * self.pricing["input"] + outputs * self.pricing["output"] +
                      writes * self.pricing["cache_write"] + reads * self.pricing["cache_read"]) / 1_000_000
            row["api_responses"] += 1
            row["input_tokens"] += inputs
            row["output_tokens"] += outputs
            row["cache_write_tokens"] += writes
            row["cache_read_tokens"] += reads
            row["estimated_usd"] = round(row["estimated_usd"] + amount, 10)
            self.data["estimated_total_usd"] = round(self.data["estimated_total_usd"] + amount, 10)
            self._save()
            self._postfix()

    def complete_batch(self, stage: str, cached: bool) -> None:
        with self.lock:
            if cached:
                self._row(stage)["local_cache_hits"] += 1
            if self.bar is not None and self.current_stage == stage:
                self.bar.update(1)
            self._save()
            self._postfix()

    def _postfix(self) -> None:
        if self.bar is not None:
            row = self.data["stages"].get(self.current_stage, {})
            model = row.get("model") or "unknown"
            self.bar.set_postfix_str(
                f"model={model} cost=${self.data['estimated_total_usd']:.4f} cache={row.get('local_cache_hits', 0)}")

    def _save(self) -> None:
        self.data["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(self.path, self.data)

    def close(self) -> None:
        with self.lock:
            if self.bar is not None:
                self.bar.close()
                self.bar = None
            self._save()

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.data))


def recovery_candidates(all_chunks: list[Chunk], baseline: list[Chunk], cfg: dict) -> list[Chunk]:
    existing = {c.id for c in baseline}
    out = []
    for chunk in all_chunks:
        text = " ".join(chunk.text.split())
        if chunk.id in existing or SHALL.search(text):
            continue
        matches = bool(NORMATIVE.search(text))
        matches |= cfg.get("include_quantitative", True) and bool(QUANTITATIVE.search(text))
        matches |= cfg.get("include_tables", True) and bool(TABLEISH.search(text))
        matches |= cfg.get("include_cross_references", True) and bool(REFERENCE.search(text))
        if matches:
            out.append(chunk)
    return out


class Experiment:
    def __init__(self, cfg: dict, directory: Path):
        self.cfg, self.directory = cfg, directory
        self.models = cfg["models"]
        self.llm = CachedLLM(directory / ".cache", self.models)
        self.product_inputs: list[dict] = []

    def product_model(self, spec: str, spec_path: Path) -> dict:
        prompt = PRODUCT_PROMPT.format(spec=spec)
        content: list[dict] = [{"type": "text", "text": prompt}]
        referenced = []
        for raw in re.findall(r"!\[[^]]*\]\(([^)]+)\)", spec):
            candidate = (spec_path.parent / raw.split()[0].strip("<>\"'")).resolve()
            if candidate.is_file():
                referenced.append(candidate)
        for candidate in sorted(spec_path.parent.iterdir()):
            if candidate.is_file() and "explod" in candidate.stem.lower() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                referenced.append(candidate.resolve())
        for image_path in dict.fromkeys(referenced):
            mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
            content.append({"type": "text", "text": f"The next image is input evidence from {image_path.name}."})
            content.append({"type": "image", "source": {"type": "base64", "media_type": mime,
                                                            "data": base64.b64encode(image_path.read_bytes()).decode("ascii")}})
            self.product_inputs.append({"path": str(image_path), "sha256": sha256_file(image_path), "media_type": mime})
        payload: str | list[dict] = content if len(content) > 1 else prompt
        return self.llm.call("product", payload, PRODUCT_SCHEMA, self.cfg["classification"]["effort"])

    def classify(self, product: dict, contexts: dict[int, ContextRecord]) -> dict[int, dict]:
        ccfg = self.cfg["classification"]
        items = sorted(contexts.items())
        batches = [items[i:i + ccfg["batch_size"]] for i in range(0, len(items), ccfg["batch_size"])]

        def one(batch: list[tuple[int, ContextRecord]]) -> dict[int, dict]:
            payload = [{"context_id": cid, **asdict(context)} for cid, context in batch]
            prompt = CLASSIFY_PROMPT.format(product=canonical_json(product), contexts=canonical_json(payload))
            data = self.llm.call("classification", prompt, DECISION_SCHEMA, ccfg["effort"])
            wanted = {cid for cid, _ in batch}
            return {d["context_id"]: d for d in data["decisions"] if d["context_id"] in wanted}

        decisions = {}
        with ThreadPoolExecutor(max_workers=ccfg["workers"]) as pool:
            for part in pool.map(one, batches):
                decisions.update(part)
        return decisions

    def run_case(self, case: str, spec_path: Path, variant: str, out: Path, trace_path: Path,
                 fixed_selection: dict[str, list[str]] | None = None) -> None:
        if variant not in {"B", "C"}:
            raise ValueError("contextual inference supports variants B and C")
        spec = spec_path.read_text(encoding="utf-8")
        progress = LiveProgressCosts(out.with_name(out.stem + "-costs.json"),
                                     self.cfg["pricing_usd_per_million_tokens"])
        self.llm.progress = progress
        if fixed_selection is None:
            from retrieval.regselect import select
            selection = select(spec, **self.cfg["regulation_selection"])
        else:
            selection = fixed_selection
        regulations = set(selection)
        corpus = [c for c in load_corpus("paragraph", "clauses") if c.regulation in regulations]
        baseline = candidates(regulations, "shall")
        recovery = recovery_candidates(corpus, baseline, self.cfg["recovery"]) if variant == "C" else []
        candidate_list = baseline + recovery
        builder = ContextBuilder(corpus, self.cfg["context"])
        contexts = {c.id: builder.build(c) for c in candidate_list}
        progress.start("product", 1, self.models["product"])
        product = self.product_model(spec, spec_path)
        progress.start("classification", ceil(len(candidate_list) / self.cfg["classification"]["batch_size"]),
                       self.models["classification"])
        decisions = self.classify(product, contexts)
        missing_decisions = sorted(set(contexts) - set(decisions))
        retain = set(self.cfg["classification"]["retain"])
        selected = [c for c in candidate_list if (d := decisions.get(c.id)) and d["contains_obligations"]
                    and d["applicability"] in retain]

        # These calls are the unchanged shared strict writer and ranked verifier.
        progress.start("strict_writer", ceil(len(selected) / 8), self.models["strict_writer"])
        previous_observer = set_usage_observer(lambda model, usage: progress.record_usage("strict_writer", model, usage))
        try:
            pairs = write(spec, selected, effort=self.cfg["writer"]["effort"], prompt=self.cfg["writer"]["prompt"],
                          on_batch=lambda cached: progress.complete_batch("strict_writer", cached),
                          model=self.models["strict_writer"])
        finally:
            set_usage_observer(previous_observer)
        pre_rank = {"team_id": self.cfg["team_id"], "case_id": case, "requirements": [
            {"id": f"R-{i:04d}", "text": text, "source": chunk.cite()} for i, (chunk, text) in enumerate(pairs, 1)]}
        progress.start("soft_ranker", ceil(len(dedupe(pre_rank["requirements"])) / 30),
                       self.models["soft_ranker"])
        previous_observer = set_usage_observer(lambda model, usage: progress.record_usage("soft_ranker", model, usage))
        try:
            ranked, rank_report = refine_ranked(
                spec, pre_rank, self.cfg["ranker"]["drop_at_or_below"], self.cfg["ranker"]["effort"],
                on_batch=lambda cached: progress.complete_batch("soft_ranker", cached),
                model=self.models["soft_ranker"])
        finally:
            set_usage_observer(previous_observer)
        progress.close()
        cost_snapshot = progress.snapshot()
        print(f"Estimated API cost for {case} Variant {variant}: ${cost_snapshot['estimated_total_usd']:.4f} USD "
              f"(see {progress.path})")
        atomic_write_json(out, ranked)
        unresolved = [{"chunk_id": cid, "references": context.unresolved_references}
                      for cid, context in contexts.items() if context.unresolved_references]
        recovery_ids = {c.id for c in recovery}
        selected_ids = {c.id for c in selected}
        recovery_sources = {(c.regulation, c.version, c.paragraph) for c in recovery}
        is_recovery_requirement = lambda r: (r["source"]["regulation"], r["source"]["version"],
                                             r["source"].get("paragraph")) in recovery_sources
        trace = {
            "variant": variant, "case_id": case, "spec": {"path": str(spec_path), "sha256": sha256_file(spec_path)},
            "config_sha256": sha256_text(canonical_json(self.cfg)), "models": self.models,
            "prompt_templates": {
                "product_sha256": sha256_text(PRODUCT_PROMPT),
                "context_classifier_sha256": sha256_text(CLASSIFY_PROMPT),
                "reused_strict_writer_sha256": sha256_text(REUSED_WRITER_PROMPTS["strict"]),
                "reused_ranker_sha256": sha256_text(REUSED_RANK_PROMPT),
            },
            "parameters": {"classification": self.cfg["classification"], "writer": self.cfg["writer"],
                           "ranker": self.cfg["ranker"], "context": self.cfg["context"],
                           "recovery": self.cfg["recovery"]},
            "selected_regulations": selection, "versions": sorted({(c.regulation, c.version) for c in corpus}),
            "product_model": product,
            "product_image_inputs": self.product_inputs,
            "counts": {"corpus": len(corpus), "baseline_candidates": len(baseline),
                       "recovery_candidates": len(recovery), "selected_clauses": len(selected),
                       "selected_recovery_clauses": len(recovery_ids & selected_ids),
                       "pre_rank_requirements": len(pre_rank["requirements"]),
                       "final_requirements": len(ranked["requirements"]),
                       "pre_rank_recovery_requirements": sum(is_recovery_requirement(r) for r in pre_rank["requirements"]),
                       "final_recovery_requirements": sum(is_recovery_requirement(r) for r in ranked["requirements"]),
                       "conditional": sum(d["applicability"] == "CONDITIONAL" for d in decisions.values()),
                       "uncertain": sum(d["applicability"] == "UNCERTAIN" for d in decisions.values())},
            "candidates": [{"chunk_id": c.id, "branch": "recovery" if c.id in recovery_ids else "baseline",
                            "source": c.cite(), "clause_id": c.meta.get("clause_id"),
                            "source_text": c.text, "text_sha256": sha256_text(c.text), "decision": decisions.get(c.id),
                            "selected": c.id in selected_ids} for c in candidate_list],
            "unresolved_references": unresolved,
            "pre_rank_requirements": pre_rank["requirements"], "rank_report": rank_report,
            "llm_calls": self.llm.events,
            "cost": cost_snapshot,
            "errors": ([{"stage": "classification", "message": "model omitted candidate ids",
                          "chunk_ids": missing_decisions}] if missing_decisions else []),
            "incomplete": bool(missing_decisions),
        }
        atomic_write_json(trace_path, trace)
