"""Tests for openskills.runtime.enforcer."""

from openskills.models import (
    Constraints,
    EvidenceItem,
    EvidenceRequirements,
    FinalizationRules,
    PlanStep,
    SkillContract,
)
from openskills.runtime.enforcer import SkillEnforcer
from openskills.runtime.evidence import EvidenceTracker


def _make_contract(**kwargs: object) -> SkillContract:
    defaults = {"openskills": "1.0", "name": "test", "description": "Test."}
    return SkillContract(**{**defaults, **kwargs})  # type: ignore[arg-type]


class TestCheckToolCall:
    def test_allowed_tool(self) -> None:
        contract = _make_contract(
            constraints=Constraints(allowed_tools=["query", "report"])
        )
        enforcer = SkillEnforcer(contract)
        result = enforcer.check_tool_call("query", {"q": "hello"})
        assert not result.blocked
        assert result.tool_name == "query"

    def test_blocked_tool(self) -> None:
        contract = _make_contract(
            constraints=Constraints(allowed_tools=["query"])
        )
        enforcer = SkillEnforcer(contract)
        result = enforcer.check_tool_call("forbidden", {})
        assert result.blocked
        assert "not in allowed_tools" in (result.block_reason or "")

    def test_rewrite_via_override(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                allowed_tools=["run_query"],
                tool_overrides={"search": "run_query"},
            )
        )
        enforcer = SkillEnforcer(contract)
        result = enforcer.check_tool_call("search", {"q": "test"})
        assert not result.blocked
        assert result.rewritten
        assert result.tool_name == "run_query"

    def test_unconstrained_allows_everything(self) -> None:
        contract = _make_contract()
        enforcer = SkillEnforcer(contract)
        result = enforcer.check_tool_call("anything", {})
        assert not result.blocked


class TestCanFinalize:
    def test_all_evidence_collected(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                evidence=EvidenceRequirements(
                    required=[EvidenceItem(id="a", description="A")]
                ),
                finalization=FinalizationRules(require_all_evidence=True),
            )
        )
        enforcer = SkillEnforcer(contract)
        tracker = EvidenceTracker(contract)
        tracker.record("a")
        assert enforcer.can_finalize(tracker)

    def test_missing_evidence_blocks(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                evidence=EvidenceRequirements(
                    required=[
                        EvidenceItem(id="a", description="A"),
                        EvidenceItem(id="b", description="B"),
                    ]
                ),
                finalization=FinalizationRules(require_all_evidence=True),
            )
        )
        enforcer = SkillEnforcer(contract)
        tracker = EvidenceTracker(contract)
        tracker.record("a")
        assert not enforcer.can_finalize(tracker)

    def test_min_iterations_blocks(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                finalization=FinalizationRules(min_iterations=3),
            )
        )
        enforcer = SkillEnforcer(contract)
        tracker = EvidenceTracker(contract)
        assert not enforcer.can_finalize(tracker)
        enforcer.increment_iteration()
        enforcer.increment_iteration()
        assert not enforcer.can_finalize(tracker)
        enforcer.increment_iteration()
        assert enforcer.can_finalize(tracker)

    def test_no_constraints_allows_immediate(self) -> None:
        contract = _make_contract()
        enforcer = SkillEnforcer(contract)
        tracker = EvidenceTracker(contract)
        assert enforcer.can_finalize(tracker)


class TestFinalizationBlockers:
    def test_lists_all_blockers(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                evidence=EvidenceRequirements(
                    required=[
                        EvidenceItem(id="x", description="X missing"),
                        EvidenceItem(id="y", description="Y missing"),
                    ]
                ),
                finalization=FinalizationRules(
                    require_all_evidence=True, min_iterations=2
                ),
            )
        )
        enforcer = SkillEnforcer(contract)
        tracker = EvidenceTracker(contract)
        blockers = enforcer.finalization_blockers(tracker)
        assert len(blockers) == 3
        assert any("Min iterations" in b for b in blockers)
        assert any("X missing" in b for b in blockers)
        assert any("Y missing" in b for b in blockers)
