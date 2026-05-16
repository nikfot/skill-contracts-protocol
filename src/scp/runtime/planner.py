"""PlanExecutor -- deterministic query-plan execution.

Extracted and generalized from elastic/sophia's InvestigatorAgent loop
(the metadata-planner section that executes query_steps before handing
control to the LLM).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from ..models import PlanStep, SkillContract


@dataclass
class ResolvedStep:
    """A plan step with tool name resolved and args_template interpolated."""

    tool: str
    description: str
    args: dict[str, Any] = field(default_factory=dict)
    original_step: PlanStep | None = None


class PlanExecutor:
    """Iterate through a contract's plan steps deterministically.

    Resolves tool_overrides and interpolates ``{{variable}}`` placeholders
    in args_template using a provided context dict.

    Usage:
        executor = PlanExecutor(contract, context={"domain": "example.com"})
        for step in executor:
            result = my_tool_runner(step.tool, step.args)
    """

    def __init__(
        self,
        contract: SkillContract,
        context: dict[str, str] | None = None,
    ) -> None:
        self._contract = contract
        self._context = context or {}
        self._steps = list(contract.plan_steps)
        self._index = 0

    @property
    def total_steps(self) -> int:
        return len(self._steps)

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def is_exhausted(self) -> bool:
        return self._index >= len(self._steps)

    def __iter__(self) -> Iterator[ResolvedStep]:
        return self

    def __next__(self) -> ResolvedStep:
        step = self.next_step()
        if step is None:
            raise StopIteration
        return step

    def next_step(self) -> ResolvedStep | None:
        """Return the next resolved step, or None if plan is exhausted."""
        if self._index >= len(self._steps):
            return None

        raw_step = self._steps[self._index]
        self._index += 1

        resolved_tool = self._contract.resolve_tool(raw_step.tool)
        args = _interpolate_args(raw_step.args_template, self._context)

        return ResolvedStep(
            tool=resolved_tool,
            description=raw_step.description,
            args=args,
            original_step=raw_step,
        )

    def reset(self) -> None:
        """Reset the executor to the beginning of the plan."""
        self._index = 0


_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def _interpolate_args(
    template: dict[str, Any] | None,
    context: dict[str, str],
) -> dict[str, Any]:
    """Resolve ``{{variable}}`` placeholders in an args_template dict."""
    if template is None:
        return {}

    result: dict[str, Any] = {}
    for key, value in template.items():
        if isinstance(value, str):
            result[key] = _PLACEHOLDER_RE.sub(
                lambda m: context.get(m.group(1), m.group(0)),
                value,
            )
        elif isinstance(value, dict):
            result[key] = _interpolate_args(value, context)
        else:
            result[key] = value
    return result
