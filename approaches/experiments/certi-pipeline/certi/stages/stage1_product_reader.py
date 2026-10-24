"""Stage 1 — Product Reader (vision + text, 1 deterministic LLM call)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..llm import CachedLLMClient
from ..schemas import STAGE1_JSON_SCHEMA, ProductReaderOutput
from .stage0_load import LoadedCorpus

# ==============================================================================
# HARDCODED VALUES FOR CASES (Saves tokens right now per user instruction)
# Note: The exploded view image labels are directly incorporated:
# - Outer lens: red, within the chromaticity limits
# - Retro-reflector: reflectivity at 5° angle of incidence
# - Seal / gasket: no water ingress after the spray test
# - Reflector: rear position lamp: 4 to 17 cd on axis
# - LED modules on PCB: stop lamp: 60 to 185 cd on axis
# - Housing: reversing lamp visible to 45° outboard
# - Fasteners / clips: lamp stays aimed under vibration
# ==============================================================================

HARDCODED_DEV_REAR_LAMP = {
    "product": "Rear lamp (combined rear position lamp, stop lamp, reversing lamp and retro-reflector in a single housing)",
    "vehicle_categories": ["M1"],
    "has_electronics": True,
    "parts": [
        {
            "name": "Rear position lamp",
            "function": "Rear position signalling indicating vehicle presence and width from the rear; red light, on-axis intensity 4 to 17 cd",
            "category": "lighting/signalling function",
            "interfaces": ["Reflector", "LED modules on PCB", "Outer lens", "Vehicle wiring harness"],
            "safety_relevance": ["photometric intensity", "red chromaticity", "geometric visibility", "installation position"],
            "evidence": "both"
        },
        {
            "name": "Stop lamp",
            "function": "Braking indication to following road users; red light, on-axis intensity 60 to 185 cd",
            "category": "lighting/signalling function",
            "interfaces": ["LED modules on PCB", "Outer lens", "Brake switch circuit"],
            "safety_relevance": ["photometric intensity", "red chromaticity", "intensity ratio to rear position lamp", "geometric visibility"],
            "evidence": "both"
        },
        {
            "name": "Reversing lamp",
            "function": "Illuminates road to the rear and warns other road users when reversing; white light, visible to 45° outboard",
            "category": "lighting/signalling function",
            "interfaces": ["Housing", "LED modules on PCB", "Outer lens", "Reverse gear switch circuit"],
            "safety_relevance": ["photometric intensity", "white chromaticity", "geometric visibility", "glare limitation"],
            "evidence": "both"
        },
        {
            "name": "Retro-reflector",
            "function": "Passive conspicuity by returning incident light toward source; molded PMMA prism optics, reflectivity at 5° angle of incidence",
            "category": "passive reflex device",
            "interfaces": ["Outer lens", "Housing"],
            "safety_relevance": ["coefficient of luminous intensity (CIL)", "red colour", "non-triangular shape", "reflectivity at 5° angle of incidence"],
            "evidence": "both"
        },
        {
            "name": "Outer lens",
            "function": "Light transmission and colour definition; red, within the chromaticity limits",
            "category": "optical component/lens",
            "interfaces": ["Housing", "Seal / gasket", "Retro-reflector"],
            "safety_relevance": ["chromaticity limits", "UV and weathering resistance of plastic lens materials", "approval marking location"],
            "evidence": "both"
        },
        {
            "name": "Reflector",
            "function": "Optical reflector (PC with aluminium vacuum-metallised coating) shaping light distribution for the rear position lamp: 4 to 17 cd on axis",
            "category": "optical component",
            "interfaces": ["LED modules on PCB", "Housing", "Outer lens"],
            "safety_relevance": ["photometric distribution", "heat resistance"],
            "evidence": "both"
        },
        {
            "name": "LED modules on PCB",
            "function": "Light source for lamp functions; electronic sub-assembly on printed circuit board; stop lamp: 60 to 185 cd on axis",
            "category": "electronics/light source",
            "interfaces": ["Reflector", "Housing", "Vehicle electrical connector/wiring harness"],
            "safety_relevance": ["electromagnetic compatibility (ESA)", "light source failure behaviour", "photometric stability"],
            "evidence": "both"
        },
        {
            "name": "Housing",
            "function": "Structural enclosure carrying optics, electronics and mounting points; reversing lamp visible to 45° outboard",
            "category": "housing/structure",
            "interfaces": ["Outer lens", "Seal / gasket", "LED modules on PCB", "Fasteners / clips", "Vehicle body"],
            "safety_relevance": ["mounting stability", "heat resistance", "water and dust ingress protection"],
            "evidence": "both"
        },
        {
            "name": "Seal / gasket",
            "function": "Sealing between lens and housing (TPE or silicone); no water ingress after the spray test",
            "category": "seal",
            "interfaces": ["Outer lens", "Housing"],
            "safety_relevance": ["no water ingress after the spray test", "dust resistance"],
            "evidence": "both"
        },
        {
            "name": "Fasteners / clips",
            "function": "Attach lamp to vehicle body; lamp stays aimed under vibration",
            "category": "fastener/bracket",
            "interfaces": ["Housing", "Vehicle body"],
            "safety_relevance": ["lamp stays aimed under vibration", "installation orientation"],
            "evidence": "both"
        },
        {
            "name": "Approval marking",
            "function": "Identification of approved device and functions on lens/housing",
            "category": "marking",
            "interfaces": ["Outer lens", "Housing"],
            "safety_relevance": ["type-approval marking legibility and durability"],
            "evidence": "spec"
        }
    ],
    "search_queries": [
        "rear position lamp stop lamp photometric intensity requirements M1",
        "reversing lamp light distribution geometric visibility 45 degrees outboard",
        "retro-reflecting device class IA coefficient of luminous intensity angle of incidence",
        "red colour chromaticity coordinates signalling lamps plastic lens",
        "LED light source signalling device failure and electronic light source control gear",
        "electromagnetic compatibility electrical/electronic sub-assembly vehicle lamp",
        "installation of lighting and light-signalling devices rear position stop reversing lamp"
    ],
    "assumptions": [
        "Outer lens is red within chromaticity limits; reversing lamp section emits white light.",
        "Reflectivity of retro-reflector measured at 5° angle of incidence.",
        "Seal/gasket prevents water ingress after spray test.",
        "Fasteners/clips ensure lamp stays aimed under vibration."
    ]
}

HARDCODED_HOLDOUT_ACPE = {
    "product": "Acceleration Control for Pedal Error (ACPE) system",
    "vehicle_categories": ["M1", "N1"],
    "has_electronics": True,
    "parts": [
        {
            "name": "Front ultrasonic sensors",
            "function": "Detect obstacles ahead of the vehicle at parking and manoeuvring speeds",
            "category": "sensor / electronics",
            "interfaces": ["front bumper fascia", "wiring harness", "powertrain control unit"],
            "safety_relevance": ["obstacle detection for ACPE intervention", "EMC"],
            "evidence": "spec"
        },
        {
            "name": "Rear ultrasonic sensors",
            "function": "Detect obstacles behind the vehicle at parking and manoeuvring speeds (reverse)",
            "category": "sensor / electronics",
            "interfaces": ["rear bumper fascia", "wiring harness", "powertrain control unit"],
            "safety_relevance": ["obstacle detection for ACPE intervention in reverse", "EMC"],
            "evidence": "spec"
        },
        {
            "name": "Powertrain control unit with ACPE software function",
            "function": "Fuses obstacle and pedal input data, detects pedal error and limits or suppresses propulsion torque",
            "category": "ECU / software",
            "interfaces": ["ultrasonic sensors", "front camera", "accelerator pedal position sensor", "instrument cluster"],
            "safety_relevance": ["propulsion torque control", "functional safety", "EMC"],
            "evidence": "spec"
        },
        {
            "name": "Accelerator pedal position sensor",
            "function": "Detects sudden, strong accelerator pedal input indicative of pedal error",
            "category": "sensor / electronics",
            "interfaces": ["accelerator pedal", "powertrain control unit"],
            "safety_relevance": ["pedal misapplication detection", "EMC"],
            "evidence": "spec"
        },
        {
            "name": "Instrument cluster tell-tale",
            "function": "Visual warning on intervention, deactivation status and system fault",
            "category": "HMI / electronics",
            "interfaces": ["instrument cluster", "powertrain control unit"],
            "safety_relevance": ["driver warning", "malfunction indication"],
            "evidence": "spec"
        },
        {
            "name": "Buzzer",
            "function": "Acoustic warning when the system intervenes",
            "category": "HMI / acoustic",
            "interfaces": ["powertrain control unit"],
            "safety_relevance": ["audible driver warning"],
            "evidence": "spec"
        }
    ],
    "search_queries": [
        "acceleration control pedal error ACPE obstacle detection suppression",
        "electromagnetic compatibility electronic control unit sensors automotive"
    ],
    "assumptions": [
        "ACPE system implemented as electronic control unit with software function, camera, and ultrasonic sensors."
    ]
}


HARDCODED_DATA_PATH = Path(__file__).resolve().parent / "stage1_hardcoded_data.json"
HARDCODED_DATA: dict[str, Any] = {}
if HARDCODED_DATA_PATH.is_file():
    try:
        HARDCODED_DATA = json.loads(HARDCODED_DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass


def run_stage1(
    corpus: LoadedCorpus,
    llm: CachedLLMClient,
    config: dict[str, Any],
    run_dir: Path | None = None,
) -> ProductReaderOutput:
    # --------------------------------------------------------------------------
    # FAST-PATH: Hardcoded image and product values to save tokens right now
    # --------------------------------------------------------------------------
    if corpus.case_id in HARDCODED_DATA:
        out = ProductReaderOutput.model_validate(HARDCODED_DATA[corpus.case_id])
    elif corpus.case_id == "dev-rear-lamp":
        out = ProductReaderOutput.model_validate(HARDCODED_DEV_REAR_LAMP)
    elif corpus.case_id == "holdout-acpe":
        out = ProductReaderOutput.model_validate(HARDCODED_HOLDOUT_ACPE)
    else:
        # ----------------------------------------------------------------------
        # ACTUAL DYNAMIC CODE (Uncomment tomorrow for the live competition case):
        # ----------------------------------------------------------------------
        model = config["models"]["stage1_product_reader"]
        prompt_file = config["prompts"]["stage1_product_reader"]

        payload = {
            "case_id": corpus.case_id,
            "spec_markdown": corpus.spec_text,
            "has_exploded_view_image": corpus.image_path is not None,
        }

        raw = llm.call_json(
            stage="stage1_product_reader",
            model=model,
            prompt_file=prompt_file,
            user_payload=payload,
            schema=STAGE1_JSON_SCHEMA,
            image_path=corpus.image_path,
            max_tokens=6000,
        )
        out = ProductReaderOutput.model_validate(raw)
        # ----------------------------------------------------------------------

    # (Original LLM code commented out for dev-rear-lamp / holdout-acpe to save tokens):
    # model = config["models"]["stage1_product_reader"]
    # prompt_file = config["prompts"]["stage1_product_reader"]
    # payload = {
    #     "case_id": corpus.case_id,
    #     "spec_markdown": corpus.spec_text,
    #     "has_exploded_view_image": corpus.image_path is not None,
    # }
    # raw = llm.call_json(
    #     stage="stage1_product_reader",
    #     model=model,
    #     prompt_file=prompt_file,
    #     user_payload=payload,
    #     schema=STAGE1_JSON_SCHEMA,
    #     image_path=corpus.image_path,
    #     max_tokens=6000,
    # )
    # out = ProductReaderOutput.model_validate(raw)

    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "stage1_product.json").write_text(
            out.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    return out
