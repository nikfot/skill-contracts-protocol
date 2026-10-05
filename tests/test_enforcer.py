"""Tests for scp.runtime.enforcer."""

from scp.models import (
    Constraints,
    EnforcementMode,
    EvidenceItem,
    EvidenceRequirements,
    FinalizationRules,
    PlanStep,
    SkillContract,
)
from scp.runtime.enforcer import SkillEnforcer
from scp.runtime.evidence import EvidenceTracker
from scp.runtime.protocol import ToolDecision


def _make_contract(**kwargs: object) -> SkillContract:
    defaults = {"scp": "1.0", "name": "test", "description": "Test."}
    return SkillContract(**{**defaults, **kwargs})  # type: ignore[arg-type]


class TestCheckToolCall:
    def test_allowed_tool(self) -> None:
        contract = _make_contract(
            constraints=Constraints(tool_ids=["query", "report"])
        )
        enforcer = SkillEnforcer(contract)
        result = enforcer.check_tool_call("query", {"q": "hello"})
        assert not result.blocked
        assert result.tool_name == "query"

    def test_blocked_tool(self) -> None:
        contract = _make_contract(
            constraints=Constraints(tool_ids=["query"])
        )
        enforcer = SkillEnforcer(contract)
        result = enforcer.check_tool_call("forbidden", {})
        assert result.blocked
        assert "not in tool_ids" in (result.block_reason or "")

    def test_rewrite_via_override(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                tool_ids=["run_query"],
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


def _plan_contract(enforcement: str = "strict", tool_ids: list[str] | None = None) -> SkillContract:
    return _make_contract(
        constraints=Constraints(
            enforcement=EnforcementMode(enforcement),
            tool_ids=tool_ids,
            plan=[
                PlanStep(tool="step_a", description="A"),
                PlanStep(tool="step_b", description="B"),
                PlanStep(tool="post_reply", description="Post", requires_evidence=["thread_read", "classified"]),
            ],
            evidence=EvidenceRequirements(
                required=[
                    EvidenceItem(id="thread_read", description="Thread read"),
                    EvidenceItem(id="classified", description="Classified"),
                ]
            ),
        )
    )


def _evaluate(
    contract: SkillContract,
    tool: str,
    *,
    evidence: tuple[str, ...] = (),
    current_step_index: int = 0,
    completed_steps: tuple[int, ...] = (),
) -> ToolDecision:
    enforcer = SkillEnforcer(contract)
    enforcer.restore_progress(current_step_index=current_step_index, completed_steps=completed_steps)
    tracker = EvidenceTracker(contract)
    tracker.record_many(list(evidence))
    return enforcer.evaluate(tool, {}, tracker)


class TestEvaluateStepOrder:
    def test_current_step_allowed(self) -> None:
        decision = _evaluate(_plan_contract(), "step_a")

        assert decision.action == "allow"
        assert decision.reason is None

    def test_future_step_blocked(self) -> None:
        decision = _evaluate(_plan_contract(), "post_reply")

        assert decision.action == "block"
        assert "step_a" in (decision.reason or "")
        assert "post_reply" in (decision.reason or "")

    def test_past_step_allowed(self) -> None:
        decision = _evaluate(_plan_contract(), "step_a", current_step_index=1, completed_steps=(0,))

        assert decision.action == "allow"

    def test_utility_tool_allowed(self) -> None:
        contract = _plan_contract(tool_ids=["step_a", "step_b", "post_reply", "utility"])

        assert _evaluate(contract, "utility").action == "allow"

    def test_no_plan_allows(self) -> None:
        assert _evaluate(_make_contract(), "anything").action == "allow"

    def test_tool_ids_violation_wins(self) -> None:
        decision = _evaluate(_plan_contract(tool_ids=["step_a"]), "post_reply")

        assert "not in tool_ids" in (decision.reason or "")


class TestEvaluateEvidenceGate:
    def test_gate_satisfied(self) -> None:
        decision = _evaluate(
            _plan_contract(), "post_reply", evidence=("thread_read", "classified"), current_step_index=2
        )

        assert decision.action == "allow"

    def test_gate_blocks_missing_evidence(self) -> None:
        decision = _evaluate(_plan_contract(), "post_reply", evidence=("thread_read",), current_step_index=2)

        assert decision.action == "block"
        assert decision.reason == (
            "Step 3 (post_reply) requires evidence: classified. Collect the missing evidence first."
        )

    def test_explicit_step_index_skips_order_and_uses_that_gate(self) -> None:
        contract = _plan_contract()
        enforcer = SkillEnforcer(contract)
        tracker = EvidenceTracker(contract)

        decision = enforcer.evaluate("post_reply", {}, tracker, step_index=2)

        assert "requires evidence: thread_read, classified" in (decision.reason or "")
        assert enforcer.evaluate("step_b", {}, tracker, step_index=1).action == "allow"


class TestEvaluateModes:
    def test_soft_warns(self) -> None:
        decision = _evaluate(_plan_contract("soft"), "post_reply")

        assert decision.action == "warn"
        assert decision.allowed
        assert decision.reason

    def test_off_allows_but_keeps_the_reason(self) -> None:
        decision = _evaluate(_plan_contract("off"), "post_reply")

        assert decision.action == "allow"
        assert decision.reason

    def test_mode_argument_overrides_contract(self) -> None:
        contract = _plan_contract("strict")
        enforcer = SkillEnforcer(contract)

        decision = enforcer.evaluate("post_reply", {}, EvidenceTracker(contract), mode=EnforcementMode.soft)

        assert decision.action == "warn"

    def test_rewrite_is_reported(self) -> None:
        contract = _make_contract(
            constraints=Constraints(tool_ids=["run_query"], tool_overrides={"search": "run_query"})
        )

        decision = SkillEnforcer(contract).evaluate("search", {"q": 1}, EvidenceTracker(contract))

        assert (decision.tool_name, decision.tool_args, decision.rewritten) == ("run_query", {"q": 1}, True)


class TestAdvance:
    def test_advances_only_on_the_current_step_tool(self) -> None:
        enforcer = SkillEnforcer(_plan_contract())

        assert enforcer.advance("step_b") is None
        assert enforcer.advance("step_a") == 0
        assert enforcer.advance("step_b") == 1
        assert (enforcer.current_step_index, enforcer.completed_steps) == (2, [0, 1])

    def test_past_the_end_does_nothing(self) -> None:
        enforcer = SkillEnforcer(_plan_contract())
        enforcer.restore_progress(current_step_index=3, completed_steps=[0, 1, 2])

        assert enforcer.advance("post_reply") is None

    def test_restore_progress(self) -> None:
        enforcer = SkillEnforcer(_plan_contract())

        enforcer.restore_progress(iteration=4, current_step_index=1, completed_steps=[0])

        assert (enforcer.iteration, enforcer.current_step_index, enforcer.completed_steps) == (4, 1, [0])
