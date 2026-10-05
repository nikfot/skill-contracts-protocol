"""Tests for scp.validator."""

from scp.models import (
    Constraints,
    EvidenceDetectionRule,
    EvidenceItem,
    EvidenceRequirements,
    PlanStep,
    ReferencedContent,
    SkillContract,
)
from scp.validator import validate_contract


class TestValidateContract:
    def test_valid_full_contract(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="good",
            description="Valid.",
            constraints=Constraints(
                tool_ids=["tool_a", "tool_b"],
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
            scp="1.0",
            name="bad-plan",
            description="Plan tool not allowed.",
            constraints=Constraints(
                tool_ids=["tool_a"],
                plan=[PlanStep(tool="tool_b", description="Wrong tool")],
            ),
        )
        errors = validate_contract(contract)
        assert len(errors) == 1
        assert "tool_b" in errors[0]
        assert "tool_ids" in errors[0]

    def test_override_target_not_in_allowed(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="bad-override",
            description="Override target not allowed.",
            constraints=Constraints(
                tool_ids=["tool_a"],
                tool_overrides={"old": "tool_c"},
            ),
        )
        errors = validate_contract(contract)
        assert len(errors) == 1
        assert "tool_c" in errors[0]

    def test_no_tool_ids_skips_checks(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="open",
            description="No tool_ids defined.",
            constraints=Constraints(
                plan=[PlanStep(tool="anything", description="Any tool ok")],
                tool_overrides={"legacy": "whatever"},
            ),
        )
        assert validate_contract(contract) == []

    def test_no_constraints(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="bare",
            description="No constraints at all.",
        )
        assert validate_contract(contract) == []

    def test_duplicate_referenced_content_names(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="dup-refs",
            description="Duplicate ref names.",
            constraints=Constraints(
                referenced_content=[
                    ReferencedContent(name="queries"),
                    ReferencedContent(name="queries"),
                ]
            ),
        )
        errors = validate_contract(contract)
        assert len(errors) == 1
        assert "queries" in errors[0]

    def test_unique_referenced_content_names(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="unique-refs",
            description="Unique ref names.",
            constraints=Constraints(
                referenced_content=[
                    ReferencedContent(name="queries"),
                    ReferencedContent(name="linux"),
                ]
            ),
        )
        assert validate_contract(contract) == []

    def test_multiple_errors(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="multi-error",
            description="Multiple issues.",
            constraints=Constraints(
                tool_ids=["tool_a"],
                plan=[
                    PlanStep(tool="bad_1", description="Bad 1"),
                    PlanStep(tool="bad_2", description="Bad 2"),
                ],
                tool_overrides={"old": "bad_3"},
            ),
        )
        errors = validate_contract(contract)
        assert len(errors) == 3


def _refs_contract(**constraints: object) -> SkillContract:
    defaults: dict[str, object] = {
        "evidence": EvidenceRequirements(required=[EvidenceItem(id="read", description="Read")]),
    }
    return SkillContract(
        scp="1.0",
        name="refs",
        description="Refs.",
        constraints=Constraints(**{**defaults, **constraints}),  # type: ignore[arg-type]
    )


class TestReferences:
    def test_requires_evidence_must_be_declared(self) -> None:
        contract = _refs_contract(plan=[PlanStep(tool="a", description="A", requires_evidence=["read", "typo"])])

        assert validate_contract(contract) == ["plan[0].requires_evidence 'typo' is not a declared evidence ID"]

    def test_detection_evidence_id_must_be_declared(self) -> None:
        evidence = EvidenceRequirements(
            required=[EvidenceItem(id="read", description="Read")],
            detection=[EvidenceDetectionRule(evidence_id="typo", tool_pattern="^a$")],
        )

        assert validate_contract(_refs_contract(evidence=evidence)) == [
            "evidence.detection[0].evidence_id 'typo' is not a declared evidence ID"
        ]

    def test_detection_patterns_must_compile(self) -> None:
        evidence = EvidenceRequirements(
            required=[EvidenceItem(id="read", description="Read")],
            detection=[EvidenceDetectionRule(evidence_id="read", tool_pattern="(", result_pattern="[")],
        )

        errors = validate_contract(_refs_contract(evidence=evidence))

        assert [e.split(" is not")[0] for e in errors] == [
            "evidence.detection[0].tool_pattern",
            "evidence.detection[0].result_pattern",
        ]

    def test_delegates_must_be_in_delegates_to(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="parent",
            description="P.",
            delegates_to=["child", "child"],
            constraints=Constraints(
                plan=[
                    PlanStep(tool="a", description="A", delegates="child"),
                    PlanStep(tool="b", description="B", delegates="other"),
                ]
            ),
        )

        assert validate_contract(contract) == [
            "Duplicate delegates_to name: 'child'",
            "plan[1].delegates 'other' is not in delegates_to",
        ]

    def test_delegates_without_delegates_to(self) -> None:
        contract = _refs_contract(plan=[PlanStep(tool="a", description="A", delegates="child")])

        assert validate_contract(contract) == ["plan[0].delegates 'child' is not in delegates_to"]


class TestOverrideAliases:
    def test_alias_cannot_target_another_alias(self) -> None:
        contract = _refs_contract(tool_overrides={"a": "b", "b": "c"})

        assert validate_contract(contract) == ["tool_overrides['a'] -> 'b' targets another alias"]

    def test_alias_cannot_be_a_plan_tool(self) -> None:
        contract = _refs_contract(
            plan=[PlanStep(tool="search", description="S")], tool_overrides={"search": "run_query"}
        )

        assert validate_contract(contract) == [
            "tool_overrides alias 'search' is a plan tool; plans must name 'run_query'"
        ]

    def test_alias_cannot_be_in_tool_ids(self) -> None:
        contract = _refs_contract(tool_ids=["search", "run_query"], tool_overrides={"search": "run_query"})

        assert validate_contract(contract) == ["tool_overrides alias 'search' is also in tool_ids"]
