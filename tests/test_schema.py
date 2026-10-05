"""Tests for scp.schema: the JSON Schema must accept everything the Pydantic models accept."""

from pathlib import Path
from typing import Any

import frontmatter
import pytest
from pydantic import BaseModel

from scp.loader import load_skill
from scp.models import (
    Activation,
    Constraints,
    EnforcementMode,
    EvidenceDetectionRule,
    EvidenceItem,
    EvidenceRequirements,
    FinalizationRules,
    InputSpec,
    PlanStep,
    ReferencedContent,
    SkillContract,
)
from scp.schema import get_schema, validate_against_schema
from scp.validator import validate_contract

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "spec" / "examples"
EXAMPLES = sorted(EXAMPLES_DIR.glob("*.yaml"))

# The body is not frontmatter; the loader adds it after parsing.
_NOT_IN_FRONTMATTER = {"content"}


def _schema_nodes() -> dict[type[BaseModel], dict[str, Any]]:
    schema = get_schema()
    defs = schema["$defs"]
    constraints = schema["properties"]["constraints"]
    return {
        SkillContract: schema,
        Activation: defs["Activation"],
        Constraints: constraints,
        PlanStep: defs["PlanStep"],
        EvidenceRequirements: constraints["properties"]["evidence"],
        EvidenceItem: defs["EvidenceItem"],
        EvidenceDetectionRule: defs["EvidenceDetectionRule"],
        FinalizationRules: constraints["properties"]["finalization"],
        InputSpec: defs["InputSpec"],
        ReferencedContent: defs["ReferencedContent"],
    }


@pytest.mark.parametrize("model", list(_schema_nodes()), ids=lambda m: m.__name__)
def test_schema_properties_match_model_fields(model: type[BaseModel]) -> None:
    node = _schema_nodes()[model]
    fields = set(model.model_fields)
    if model is SkillContract:
        fields -= _NOT_IN_FRONTMATTER

    assert set(node["properties"]) == fields


def test_enforcement_enum_matches_model() -> None:
    enforcement = get_schema()["properties"]["constraints"]["properties"]["enforcement"]

    assert enforcement["enum"] == [mode.value for mode in EnforcementMode]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_every_example_passes_schema_and_validator(path: Path) -> None:
    metadata = dict(frontmatter.loads(path.read_text(encoding="utf-8")).metadata)

    assert validate_against_schema(metadata) == []
    assert validate_contract(load_skill(path)) == []


def test_evidence_gates_and_detection_are_accepted() -> None:
    contract = {
        "scp": "1.0",
        "name": "gated",
        "description": "Gated.",
        "delegates_to": ["child"],
        "constraints": {
            "enforcement": "soft",
            "plan": [
                {"tool": "read", "description": "Read"},
                {"tool": "child", "description": "Delegate", "delegates": "child", "requires_evidence": ["read_done"]},
            ],
            "evidence": {
                "required": [{"id": "read_done", "description": "Read finished."}],
                "detection": [{"evidence_id": "read_done", "tool_pattern": "^read$", "result_pattern": "ok"}],
            },
        },
    }

    assert validate_against_schema(contract) == []


def test_unknown_enforcement_mode_is_rejected() -> None:
    contract = {"scp": "1.0", "name": "bad", "description": "Bad.", "constraints": {"enforcement": "loose"}}

    assert any("enforcement" in error for error in validate_against_schema(contract))


def test_detection_rule_requires_tool_pattern() -> None:
    contract = {
        "scp": "1.0",
        "name": "bad",
        "description": "Bad.",
        "constraints": {
            "evidence": {
                "required": [{"id": "a", "description": "A."}],
                "detection": [{"evidence_id": "a"}],
            }
        },
    }

    assert any("tool_pattern" in error for error in validate_against_schema(contract))
