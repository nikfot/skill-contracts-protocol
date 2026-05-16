"""Tests for openskills.validator."""

from openskills.models import (
    Constraints,
    EvidenceItem,
    EvidenceRequirements,
    PlanStep,
    SkillContract,
)
from openskills.validator import validate_contract


class TestValidateContract:
    def test_valid_full_contract(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="good",
            description="Valid.",
            constraints=Constraints(
                allowed_tools=["tool_a", "tool_b"],
                plan=[PlanStep(tool="tool_a", description="Step 1")],
                evidence=EvidenceRequirements(
                    required=[EvidenceItem(id="data_ok", description="Data present")]
                ),
                tool_overrides={"old": "tool_b"},
            ),
        )
        assert validate_contract(contract) == []

    def test_plan_tool_not_in_allowed(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="bad-plan",
            description="Plan tool not allowed.",
            constraints=Constraints(
                allowed_tools=["tool_a"],
                plan=[PlanStep(tool="tool_b", description="Wrong tool")],
            ),
        )
        errors = validate_contract(contract)
        assert len(errors) == 1
        assert "tool_b" in errors[0]
        assert "allowed_tools" in errors[0]

    def test_override_target_not_in_allowed(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="bad-override",
            description="Override target not allowed.",
            constraints=Constraints(
                allowed_tools=["tool_a"],
                tool_overrides={"old": "tool_c"},
            ),
        )
        errors = validate_contract(contract)
        assert len(errors) == 1
        assert "tool_c" in errors[0]

    def test_no_allowed_tools_skips_checks(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="open",
            description="No allowed_tools defined.",
            constraints=Constraints(
                plan=[PlanStep(tool="anything", description="Any tool ok")],
                tool_overrides={"legacy": "whatever"},
            ),
        )
        assert validate_contract(contract) == []

    def test_no_constraints(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="bare",
            description="No constraints at all.",
        )
        assert validate_contract(contract) == []

    def test_multiple_errors(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="multi-error",
            description="Multiple issues.",
            constraints=Constraints(
                allowed_tools=["tool_a"],
                plan=[
                    PlanStep(tool="bad_1", description="Bad 1"),
                    PlanStep(tool="bad_2", description="Bad 2"),
                ],
                tool_overrides={"old": "bad_3"},
            ),
        )
        errors = validate_contract(contract)
        assert len(errors) == 3
