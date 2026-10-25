"""Pydantic schemas and JSON schema definitions for all pipeline stages and outputs."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    regulation: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    page: int = Field(..., ge=1)
    paragraph: str | None = None


class SubmissionRequirement(BaseModel):
    id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1, max_length=2000)
    source: SourceCitation
    test_case: str | None = None


class SubmissionDocument(BaseModel):
    team_id: str = Field(..., min_length=1)
    case_id: str = Field(..., min_length=1)
    requirements: list[SubmissionRequirement] = Field(default_factory=list, max_length=5000)


class ProductPart(BaseModel):
    name: str
    function: str
    category: str
    interfaces: list[str] = Field(default_factory=list)
    safety_relevance: list[str] = Field(default_factory=list)
    evidence: Literal["spec", "image", "both"]


class ProductReaderOutput(BaseModel):
    product: str
    vehicle_categories: list[str] = Field(default_factory=list)
    has_electronics: bool = False
    parts: list[ProductPart] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class RegulationGateDecision(BaseModel):
    regulation: str
    applicable: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str
    matched_parts: list[str] = Field(default_factory=list)
    supporting_paragraphs: list[str] = Field(default_factory=list)


class ExtractedObligation(BaseModel):
    clause_id: str
    sub_paragraph: str | None = None
    text: str
    paragraph: str
    page: int
    type: Literal[
        "limit",
        "test",
        "marking",
        "installation",
        "definition-derived",
        "documentation",
        "other",
    ] = "other"
    condition: str | None = None
    measurable: bool = False
    quote_anchor: str = ""
    confidence: float = 0.9
    subject: str = "product"
    rating: int = 5
    needs_review: bool = False
    stage_origin: str = "stage3_pass1"


# JSON Schemas for Anthropic Structured Outputs (`output_config.format.schema`)
def obj(**properties) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


def array(items: dict) -> dict:
    return {"type": "array", "items": items}


STRING = {"type": "string"}
BOOL = {"type": "boolean"}
NUMBER = {"type": "number"}
INT = {"type": "integer"}

STAGE1_JSON_SCHEMA = obj(
    product=STRING,
    vehicle_categories=array(STRING),
    has_electronics=BOOL,
    parts=array(
        obj(
            name=STRING,
            function=STRING,
            category=STRING,
            interfaces=array(STRING),
            safety_relevance=array(STRING),
            evidence={"type": "string", "enum": ["spec", "image", "both"]},
        )
    ),
    search_queries=array(STRING),
    assumptions=array(STRING),
)

STAGE2_GATE_JSON_SCHEMA = obj(
    decisions=array(
        obj(
            regulation=STRING,
            applicable=BOOL,
            confidence=NUMBER,
            reason=STRING,
            matched_parts=array(STRING),
            supporting_paragraphs=array(STRING),
        )
    )
)

STAGE3_EXTRACTOR_JSON_SCHEMA = obj(
    clause_decisions=array(
        obj(
            clause_id=STRING,
            status={
                "type": "string",
                "enum": ["extracted", "not_an_obligation", "not_applicable"],
            },
            reason=STRING,
            obligations=array(
                obj(
                    sub_paragraph=STRING,
                    text=STRING,
                    type={
                        "type": "string",
                        "enum": [
                            "limit",
                            "test",
                            "marking",
                            "installation",
                            "definition-derived",
                            "documentation",
                            "other",
                        ],
                    },
                    condition=STRING,
                    measurable=BOOL,
                    quote_anchor=STRING,
                )
            ),
        )
    )
)

STAGE5_VERIFIER_JSON_SCHEMA = obj(
    verdicts=array(
        obj(
            item_id=STRING,
            action={"type": "string", "enum": ["KEEP", "FIX", "SPLIT", "DROP"]},
            faithfulness={"type": "string", "enum": ["supported", "partially", "unsupported"]},
            applies={"type": "string", "enum": ["true", "false", "borderline"]},
            confidence=NUMBER,
            reason=STRING,
            repaired_items=array(
                obj(
                    sub_paragraph=STRING,
                    text=STRING,
                )
            ),
        )
    )
)
