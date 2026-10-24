"""Shared Claude client for every LLM step (regulation selection now; clause classification / requirement writing next).

The API key is read from ANTHROPIC_API_KEY, or from a git-ignored `.env` file at the repo root or in approaches/Devansh/
containing a line `ANTHROPIC_API_KEY=...`. Never commit the key.
"""

from __future__ import annotations

import json
import os

from .corpus import APPROACH_DIR, REPO_ROOT

MODEL = "claude-opus-5-5"


def load_env() -> None:
    for path in (APPROACH_DIR / ".env", REPO_ROOT / ".env"):
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                key, sep, value = line.strip().partition("=")
                if sep and not key.startswith("#") and key.strip() not in os.environ:
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")


def structured(prompt: str, schema: dict, model: str = MODEL, effort: str = "high", max_tokens: int = 16000) -> dict:
    """One Claude call whose answer is JSON matching `schema` (structured outputs)."""
    import anthropic

    load_env()
    client = anthropic.Anthropic()
    params = dict(
        model=model,
        max_tokens=max_tokens,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # re-run on a fallback model if the request is declined
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    if max_tokens > 16000:
        # long outputs (deep thinking) must stream, or the SDK refuses the request
        with client.beta.messages.stream(**params) as stream:
            response = stream.get_final_message()
    else:
        response = client.beta.messages.create(**params)
    if response.stop_reason == "refusal":
        raise RuntimeError(f"model declined: {response.stop_details}")
    return json.loads(next(b.text for b in response.content if b.type == "text"))
