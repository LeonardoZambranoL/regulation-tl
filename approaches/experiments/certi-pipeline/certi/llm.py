"""Deterministic disk-cached Anthropic Claude & Gemini Embedding wrapper.

Rule 1: Every LLM call is a single request with a fixed, versioned prompt and a JSON-schema-validated response. Retry only on schema/API failure (max 2), same prompt.
Rule 2: Temperature 0 where supported, fixed model name per stage in config.yaml, prompts stored in prompts/<stage>_v<N>.md.
Rule 3: Cache EVERY LLM and embedding call on disk keyed by sha256(model + prompt_version + rendered_input). A rerun with unchanged inputs makes zero API calls. Supports --no-cache.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import certifi
import jsonschema
import numpy as np

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[2]
CACHE_DIR = EXP_DIR / ".cache"
LLM_CACHE_DIR = CACHE_DIR / "llm"
EMB_CACHE_DIR = CACHE_DIR / "embeddings"
PROMPTS_DIR = EXP_DIR / "prompts"


def load_env() -> None:
    """Load API keys from .env files without overriding existing env vars."""
    for path in (EXP_DIR / ".env", REPO_ROOT / ".env"):
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ and value:
                    os.environ[key] = value


def load_prompt(prompt_filename: str) -> tuple[str, str]:
    """Return (prompt_version_tag, prompt_text) from prompts/<filename>."""
    path = PROMPTS_DIR / prompt_filename
    text = path.read_text(encoding="utf-8").strip()
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    version_tag = f"{path.stem}:{content_hash}"
    return version_tag, text


def encode_image_block(image_path: Path | None) -> dict[str, Any] | None:
    """Encode a PNG/JPEG image for Anthropic Messages API."""
    if not image_path or not image_path.is_file():
        return None
    mime_type, _ = mimetypes.guess_type(str(image_path))
    mime_type = mime_type or "image/png"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": b64,
        },
    }


class CachedLLMClient:
    """Thread-safe disk-cached Anthropic Messages API client with JSON schema validation."""

    def __init__(self, use_cache: bool = True):
        load_env()
        self.use_cache = use_cache
        LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        EMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.stats = {
            "api_calls": 0,
            "cache_hits": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "emb_api_calls": 0,
            "emb_cache_hits": 0,
        }

    def call_json(
        self,
        *,
        stage: str,
        model: str,
        prompt_file: str,
        user_payload: dict[str, Any] | str,
        schema: dict[str, Any],
        image_path: Path | None = None,
        max_tokens: int = 12000,
    ) -> dict[str, Any]:
        """Make a single deterministic structured LLM call, cached on disk by sha256(model + prompt_version + rendered_input)."""
        prompt_version, system_prompt = load_prompt(prompt_file)
        rendered_input = (
            user_payload
            if isinstance(user_payload, str)
            else json.dumps(user_payload, sort_keys=True, ensure_ascii=False)
        )
        img_hash = ""
        if image_path and image_path.is_file():
            img_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()[:16]

        schema_hash = hashlib.sha256(json.dumps(schema, sort_keys=True).encode("utf-8")).hexdigest()[:12]
        cache_key_material = f"{model}|{prompt_version}|{schema_hash}|{img_hash}|{rendered_input}"
        cache_key = hashlib.sha256(cache_key_material.encode("utf-8")).hexdigest()
        cache_path = LLM_CACHE_DIR / f"{stage}_{cache_key}.json"

        if self.use_cache and cache_path.is_file():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                result = cached["result"]
                jsonschema.validate(result, schema)
                with self._lock:
                    self.stats["cache_hits"] += 1
                return result
            except Exception:
                pass

        if os.environ.get("CERTI_OFFLINE", "1") == "1":
            raise RuntimeError(
                f"CERTI_OFFLINE: cache miss for stage={stage!r}, model={model!r}. "
                "External API calls are disabled."
            )

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not found in environment or .env")

        content: list[dict[str, Any]] = [{"type": "text", "text": rendered_input}]
        img_block = encode_image_block(image_path)
        if img_block is not None:
            content.append(img_block)

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content}],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": schema,
                }
            },
        }

        last_err = None
        for attempt in range(3):  # Initial try + max 2 retries per Rule 1
            try:
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=json.dumps(body).encode("utf-8"),
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=240, context=SSL_CONTEXT) as resp:
                    data = json.load(resp)

                usage = data.get("usage", {})
                with self._lock:
                    self.stats["api_calls"] += 1
                    self.stats["input_tokens"] += usage.get("input_tokens", 0)
                    self.stats["output_tokens"] += usage.get("output_tokens", 0)

                if data.get("stop_reason") != "end_turn":
                    raise ValueError(f"Unexpected stop_reason: {data.get('stop_reason')}")

                text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
                if not text_blocks:
                    raise ValueError("No text block in Claude response")

                parsed = json.loads(text_blocks[0])
                jsonschema.validate(parsed, schema)

                # Atomic write to cache
                tmp_path = cache_path.with_suffix(".tmp")
                tmp_path.write_text(
                    json.dumps(
                        {
                            "stage": stage,
                            "model": model,
                            "prompt_version": prompt_version,
                            "cache_key": cache_key,
                            "usage": usage,
                            "result": parsed,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                tmp_path.replace(cache_path)
                return parsed

            except urllib.error.HTTPError as err:
                err_body = err.read().decode("utf-8", errors="replace")[:500]
                last_err = f"HTTP {err.code}: {err_body}"
                if err.code not in (429, 500, 502, 503, 504, 529):
                    raise RuntimeError(f"Claude API failed ({last_err})") from err
            except Exception as err:
                last_err = str(err)

            if attempt < 2:
                time.sleep(2 ** (attempt + 1))

        raise RuntimeError(f"Stage {stage} failed after 3 attempts: {last_err}")

    def embed_query(self, text: str, model: str = "gemini-embedding-2-preview", dim: int = 768) -> np.ndarray:
        """Disk-cached query embedding via Gemini REST API."""
        cache_key = hashlib.sha256(f"{model}|{dim}|{text}".encode("utf-8")).hexdigest()
        cache_path = EMB_CACHE_DIR / f"q_{cache_key}.npy"
        if self.use_cache and cache_path.is_file():
            with self._lock:
                self.stats["emb_cache_hits"] += 1
            return np.load(cache_path)

        if os.environ.get("CERTI_OFFLINE", "1") == "1":
            raise RuntimeError(
                f"CERTI_OFFLINE: cache miss for embed_query ({model}). "
                "External API calls are disabled."
            )

        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY / GEMINI_API_KEY not found for query embedding")

        body = {
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": dim,
        }
        last_err = None
        for attempt in range(3):
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent",
                data=json.dumps(body).encode("utf-8"),
                headers={"content-type": "application/json", "x-goog-api-key": api_key},
            )
            try:
                with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as resp:
                    values = json.load(resp)["embedding"]["values"]
                vec = np.asarray(values, dtype=np.float32)
                norm = float(np.linalg.norm(vec))
                if norm == 0.0:
                    raise ValueError("Zero embedding vector")
                vec = vec / norm
                with self._lock:
                    self.stats["emb_api_calls"] += 1
                np.save(cache_path, vec)
                return vec
            except Exception as err:
                last_err = str(err)
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
        raise RuntimeError(f"Gemini embedding failed: {last_err}")
