from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "approaches" / "experiments" / "devansh-toolkit" / "src"))

from experiment import ContextBuilder, LiveProgressCosts, recovery_candidates
from retrieval.corpus import Chunk


def chunk(identifier: int, paragraph: str, text: str) -> Chunk:
    return Chunk(identifier, "UN R999", "1.0.0", identifier + 1, paragraph, text,
                 meta={"pages": [identifier + 1], "clause_id": f"UN_R999_base:{identifier}"})


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            chunk(0, "1", "Scope This Regulation applies to widgets."),
            chunk(1, "2.1", "Sensor means a device that detects obstacles."),
            chunk(2, "5", "Requirements for the widget sensor."),
            chunk(3, "5.1", "The sensor shall comply with paragraph 5.2."),
            chunk(4, "5.2", "Response time: not more than 200 ms."),
            chunk(5, "5.3", "Explanatory note only."),
        ]

    def test_context_resolves_parent_scope_definition_reference_and_neighbors(self):
        builder = ContextBuilder(self.chunks, {"ancestor_depth": 3, "nearby_before": 1, "nearby_after": 1,
                                                "resolve_cross_references": True, "max_references": 8,
                                                "max_context_chars": 20000})
        result = builder.build(self.chunks[3])
        self.assertEqual(result.target["paragraph"], "5.1")
        self.assertEqual(result.parents_and_headings[0]["paragraph"], "5")
        self.assertEqual(result.governing_scope[0]["paragraph"], "1")
        self.assertEqual(result.referenced_clauses[0]["paragraph"], "5.2")
        self.assertFalse(result.unresolved_references)
        self.assertIn("5.2", {x["paragraph"] for x in result.nearby_clauses})

    def test_recovery_finds_quantitative_non_shall_and_excludes_shall(self):
        baseline = [self.chunks[3]]
        found = recovery_candidates(self.chunks, baseline, {"include_quantitative": True,
                                                            "include_cross_references": True,
                                                            "include_tables": True})
        self.assertIn(self.chunks[4], found)
        self.assertNotIn(self.chunks[3], found)

    def test_progress_costs_prices_usage_and_cache_hits(self):
        class Bar:
            def __init__(self, **kwargs):
                self.n = 0
            def update(self, amount):
                self.n += amount
            def set_postfix_str(self, value):
                pass
            def close(self):
                pass

        fake_tqdm = types.ModuleType("tqdm")
        fake_tqdm.tqdm = lambda **kwargs: Bar(**kwargs)
        pricing = {"input": 4.0, "output": 20.0, "cache_write": 5.0, "cache_read": .2}
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, {"tqdm": fake_tqdm}):
            tracker = LiveProgressCosts(Path(temp) / "costs.json", pricing)
            tracker.start("classification", 2, "test-model")
            tracker.record_usage("classification", "test-model", {
                "input_tokens": 1_000_000, "output_tokens": 1_000_000,
                "cache_creation_input_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000,
            })
            tracker.complete_batch("classification", cached=False)
            tracker.complete_batch("classification", cached=True)
            tracker.close()
            snapshot = tracker.snapshot()
        self.assertAlmostEqual(snapshot["estimated_total_usd"], 29.2)
        self.assertEqual(snapshot["stages"]["classification"]["local_cache_hits"], 1)


if __name__ == "__main__":
    unittest.main()
