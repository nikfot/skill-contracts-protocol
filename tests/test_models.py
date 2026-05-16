"""Tests for openskills.models."""

import pytest
from pydantic import ValidationError

from openskills.models import (
    Activation,
    Constraints,
    EvidenceItem,
    EvidenceRequirements,
    FinalizationRules,
    PlanStep,
    ReferencedContent,
    SkillContract,
)


class TestEvidenceItem:
    def test_valid(self) -> None:
        item = EvidenceItem(id="data_presence", description="Data exists.")
        assert item.id == "data_presence"

    def test_invalid_id_pattern(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceItem(id="Invalid-ID", description="Bad.")

    def test_empty_id(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceItem(id="", description="Empty.")


class TestEvidenceRequirements:
    def test_duplicate_ids_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate"):
            EvidenceRequirements(
                required=[
                    EvidenceItem(id="a", description="A"),
                    EvidenceItem(id="a", description="A again"),
                ]
            )

    def test_empty_required_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceRequirements(required=[])


class TestPlanStep:
    def test_with_args_template(self) -> None:
        step = PlanStep(
            tool="run_query",
            description="Fetch data",
            args_template={"query": "FROM index | LIMIT 10"},
        )
        assert step.args_template is not None
        assert "{{" not in step.args_template["query"]

    def test_without_args_template(self) -> None:
        step = PlanStep(tool="read_skill", description="Read skill doc")
        assert step.args_template is None


class TestFinalizationRules:
    def test_defaults(self) -> None:
        rules = FinalizationRules()
        assert rules.require_all_evidence is True
        assert rules.min_iterations == 0

    def test_negative_iterations_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FinalizationRules(min_iterations=-1)


class TestSkillContract:
    def test_minimal_valid(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="test-skill",
            description="A test skill.",
        )
        assert contract.tool_ids is None
        assert contract.plan_steps == []
        assert contract.required_evidence == []
        assert contract.finalization.require_all_evidence is True

    def test_full_contract(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="full-skill",
            description="Full featured.",
            activation=Activation(triggers=["test"]),
            constraints=Constraints(
                tool_ids=["tool_a", "tool_b"],
                plan=[PlanStep(tool="tool_a", description="Step 1")],
                evidence=EvidenceRequirements(
                    required=[EvidenceItem(id="data_ok", description="Data present")]
                ),
                finalization=FinalizationRules(require_all_evidence=True, min_iterations=2),
                tool_overrides={"old_tool": "tool_a"},
            ),
        )
        assert contract.tool_ids == {"tool_a", "tool_b"}
        assert len(contract.plan_steps) == 1
        assert len(contract.required_evidence) == 1
        assert contract.finalization.min_iterations == 2
        assert contract.resolve_tool("old_tool") == "tool_a"
        assert contract.resolve_tool("tool_b") == "tool_b"

    def test_is_tool_allowed_with_whitelist(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="gated",
            description="Tool gated.",
            constraints=Constraints(tool_ids=["run_query"]),
        )
        assert contract.is_tool_allowed("run_query") is True
        assert contract.is_tool_allowed("forbidden_tool") is False

    def test_is_tool_allowed_unconstrained(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="open",
            description="No constraints.",
        )
        assert contract.is_tool_allowed("anything") is True

    def test_is_tool_allowed_via_override(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="override",
            description="With override.",
            constraints=Constraints(
                tool_ids=["run_query"],
                tool_overrides={"legacy_search": "run_query"},
            ),
        )
        assert contract.is_tool_allowed("legacy_search") is True

    def test_referenced_content_property(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="with-refs",
            description="Has referenced content.",
            constraints=Constraints(
                referenced_content=[
                    ReferencedContent(name="queries", path="./queries", content="SELECT 1"),
                    ReferencedContent(name="linux", required=True),
                ]
            ),
        )
        assert len(contract.referenced_content) == 2
        assert contract.referenced_content[0].name == "queries"
        assert contract.referenced_content[1].required is True

    def test_referenced_content_empty_by_default(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="no-refs",
            description="No refs.",
        )
        assert contract.referenced_content == []

    def test_wrong_spec_version(self) -> None:
        with pytest.raises(ValidationError):
            SkillContract(
                openskills="2.0",
                name="bad-version",
                description="Wrong version.",
            )
