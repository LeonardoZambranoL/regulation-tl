"""Unit tests for Stage 0 Annex/Part/Table repair, citation_check, paragraph normalisation, deduplication, and schema validation."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[2]
sys.path.insert(0, str(EXP_DIR))
sys.path.insert(0, str(REPO_ROOT / "approaches" / "benchmarking"))

from challenge_tools.score_local import _paragraph_key  # noqa: E402
from challenge_tools.validate import validate as official_validate  # noqa: E402
from certi.schemas import ExtractedObligation, SourceCitation, SubmissionDocument, SubmissionRequirement  # noqa: E402
from certi.stages.stage0_load import load_stage0  # noqa: E402
from certi.stages.stage5_verify import citation_check_and_repair, deduplicate_obligations  # noqa: E402


class TestCertiPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_stage0("dev-rear-lamp")

    def test_stage0_loads_all_56_regulations(self) -> None:
        self.assertEqual(len(self.corpus.regulations), 56)
        self.assertEqual(len(self.corpus.all_clauses), 26769)

    def test_stage0_repairs_false_annex_jump_in_r150(self) -> None:
        # In raw UN_R150_base.json, Annex 2 1.2 (page 25) and Annex 4 Part 1 1.2 (page 28) were mislabeled Annex 5
        self.assertIn(("UN R150", _paragraph_key("Annex 2 1.2")), self.corpus.sub_para_to_clause)
        self.assertIn(("UN R150", _paragraph_key("Annex 4 Part 1 1.2")), self.corpus.sub_para_to_clause)
        self.assertIn(("UN R150", _paragraph_key("5.1.4.4.1. Table 3")), self.corpus.sub_para_to_clause)
        self.assertIn(("UN R150", _paragraph_key("Annex 6 Part 6 3. Table A6-1")), self.corpus.sub_para_to_clause)

    def test_citation_check_and_repair(self) -> None:
        ob = ExtractedObligation(
            clause_id="UN_R150_base:141",
            sub_paragraph="Annex 2, 1.2.",
            text="The conformity requirements shall be considered satisfied...",
            paragraph="Annex 2, 1.2.",
            page=25,
        )
        repaired, msg = citation_check_and_repair(ob, self.corpus)
        self.assertIsNotNone(repaired)
        self.assertEqual(msg, "ok")
        self.assertEqual(_paragraph_key(repaired.paragraph), "annex 2 1.2")

    def test_deduplication_preserves_distinct_numbers(self) -> None:
        ob1 = ExtractedObligation(
            clause_id="UN_R148_base:10",
            paragraph="5.1",
            page=10,
            text="The luminous intensity shall not be less than 40 cd.",
        )
        ob2 = ExtractedObligation(
            clause_id="UN_R148_base:10",
            paragraph="5.1",
            page=10,
            text="The luminous intensity shall not be less than 60 cd.",
        )
        ob3 = ExtractedObligation(
            clause_id="UN_R148_base:10",
            paragraph="5.1",
            page=10,
            text="The luminous intensity shall not be less than 40 cd.",
        )
        deduped, dropped = deduplicate_obligations([ob1, ob2, ob3])
        self.assertEqual(len(deduped), 2)
        self.assertEqual(dropped, 1)

    def test_submission_schema_validation(self) -> None:
        doc = SubmissionDocument(
            team_id="regulation-tl",
            case_id="dev-rear-lamp",
            requirements=[
                SubmissionRequirement(
                    id="R-0001",
                    text="The markings shall be clearly legible and indelible.",
                    source=SourceCitation(
                        regulation="UN R150",
                        version="1.2.1",
                        page=7,
                        paragraph="3.3.1.2",
                    ),
                )
            ],
        )
        problems = official_validate(
            doc.model_dump(exclude_none=True),
            kind="main",
            index=self.corpus.index_raw,
            strict=True,
        )
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
