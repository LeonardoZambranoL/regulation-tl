"""Shared Gemini embedding call used by ingestion and retrieval."""

import json
import time
import urllib.error
import urllib.request

import numpy as np


def embed_text(text, *, model, dimensions, api_key):
    body = {
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": dimensions,
    }
    for attempt in range(3):
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json", "x-goog-api-key": api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                values = json.load(response)["embedding"]["values"]
            vector = np.asarray(values, dtype=np.float32)
            if vector.shape != (dimensions,) or not np.isfinite(vector).all():
                raise ValueError("Gemini returned an invalid vector")
            norm = np.linalg.norm(vector)
            if norm == 0:
                raise ValueError("Gemini returned a zero vector")
            return vector / norm
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:500]
            if error.code not in (429, 500, 502, 503, 504, 529):
                raise RuntimeError(f"Gemini HTTP {error.code}: {detail}") from None
            last = f"Gemini HTTP {error.code}: {detail}"
        except (urllib.error.URLError, TimeoutError) as error:
            last = str(error)
        if attempt < 2:
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"Gemini embedding failed after three attempts: {last}")
