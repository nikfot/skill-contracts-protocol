"""Tests for scp.runtime.planner."""

from scp.models import (
    Constraints,
    PlanStep,
    SkillContract,
)
from scp.runtime.planner import PlanExecutor


def _make_contract(
    steps: list[PlanStep],
    overrides: dict[str, str] | None = None,
) -> SkillContract:
    return SkillContract(
        scp="1.0",
        name="test",
        description="Test.",
        constraints=Constraints(
            plan=steps,
            tool_overrides=overrides,
        ),
    )


class TestPlanExecutor:
    def test_iterate_all_steps(self) -> None:
        steps = [
            PlanStep(tool="tool_a", description="Step 1"),
            PlanStep(tool="tool_b", description="Step 2"),
        ]
        executor = PlanExecutor(_make_contract(steps))
        resolved = list(executor)
        assert len(resolved) == 2
        assert resolved[0].tool == "tool_a"
        assert resolved[1].tool == "tool_b"

    def test_tool_override_applied(self) -> None:
        steps = [PlanStep(tool="legacy_search", description="Search")]
        overrides = {"legacy_search": "run_query"}
        executor = PlanExecutor(_make_contract(steps, overrides))
        step = executor.next_step()
        assert step is not None
        assert step.tool == "run_query"

    def test_args_template_interpolation(self) -> None:
        steps = [
            PlanStep(
                tool="query",
                description="Fetch",
                args_template={"q": "FROM index | WHERE domain == '{{domain}}'", "limit": 100},
            )
        ]
        executor = PlanExecutor(
            _make_contract(steps),
            context={"domain": "example.com"},
        )
        step = executor.next_step()
        assert step is not None
        assert step.args["q"] == "FROM index | WHERE domain == 'example.com'"
        assert step.args["limit"] == 100

    def test_unresolved_placeholder_preserved(self) -> None:
        steps = [
            PlanStep(
                tool="query",
                description="Fetch",
                args_template={"q": "SELECT * WHERE x = '{{unknown}}'"},
            )
        ]
        executor = PlanExecutor(_make_contract(steps), context={})
        step = executor.next_step()
        assert step is not None
        assert "{{unknown}}" in step.args["q"]

    def test_empty_plan(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="empty",
            description="No plan.",
        )
        executor = PlanExecutor(contract)
        assert executor.is_exhausted
        assert executor.next_step() is None

    def test_exhaustion(self) -> None:
        steps = [PlanStep(tool="a", description="Only step")]
        executor = PlanExecutor(_make_contract(steps))
        assert not executor.is_exhausted
        executor.next_step()
        assert executor.is_exhausted
        assert executor.next_step() is None

    def test_reset(self) -> None:
        steps = [PlanStep(tool="a", description="Step")]
        executor = PlanExecutor(_make_contract(steps))
        executor.next_step()
        assert executor.is_exhausted
        executor.reset()
        assert not executor.is_exhausted
        step = executor.next_step()
        assert step is not None
        assert step.tool == "a"

    def test_nested_args_template(self) -> None:
        steps = [
            PlanStep(
                tool="query",
                description="Nested",
                args_template={
                    "outer": {"inner": "value_{{x}}"},
                    "flat": "{{y}}_end",
                },
            )
        ]
        executor = PlanExecutor(
            _make_contract(steps),
            context={"x": "1", "y": "2"},
        )
        step = executor.next_step()
        assert step is not None
        assert step.args["outer"]["inner"] == "value_1"
        assert step.args["flat"] == "2_end"

    def test_total_steps(self) -> None:
        steps = [
            PlanStep(tool="a", description="A"),
            PlanStep(tool="b", description="B"),
            PlanStep(tool="c", description="C"),
        ]
        executor = PlanExecutor(_make_contract(steps))
        assert executor.total_steps == 3
