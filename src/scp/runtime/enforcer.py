"""SkillEnforcer -- tool gating, rewriting, and finalization control.

Extracted and generalized from elastic/sophia's DefaultRuntime and
InvestigatorAgent loop.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..models import EnforcementMode, SkillContract
from .evidence import EvidenceTracker
from .protocol import ToolAction, ToolDecision, ToolRewrite


class SkillEnforcer:
    """Enforces a SkillContract at runtime.

    Responsibilities:
    - Gate tool calls against tool_ids
    - Rewrite tool names via tool_overrides
    - Enforce plan step order and evidence-gated steps
    - Apply the enforcement mode (strict, soft, off)
    - Decide when the agent may finalize
    - Support contract stacking for delegation
    """

    def __init__(self, contract: SkillContract) -> None:
        self._contract = contract
        self._iteration = 0
        self._delegation_stack: list[SkillContract] = []
        self._step_index = 0
        self._completed_steps: set[int] = set()

    @property
    def contract(self) -> SkillContract:
        return self._contract

    @property
    def iteration(self) -> int:
        return self._iteration

    @property
    def current_step_index(self) -> int:
        """Index of the next plan step to run."""
        return self._step_index

    @property
    def completed_steps(self) -> list[int]:
        return sorted(self._completed_steps)

    def restore_progress(
        self,
        *,
        iteration: int = 0,
        current_step_index: int = 0,
        completed_steps: Iterable[int] = (),
    ) -> None:
        """Rebuild progress for hosts that persist it between calls, such as per-process hooks."""
        self._iteration = iteration
        self._step_index = current_step_index
        self._completed_steps = set(completed_steps)

    @property
    def active_delegation(self) -> SkillContract | None:
        """The currently active delegated contract, or None."""
        if self._delegation_stack:
            return self._delegation_stack[-1]
        return None

    def push_delegation(self, child_contract: SkillContract) -> None:
        """Push a child contract onto the delegation stack.

        While delegated, the child's tool_ids are merged with the parent's
        allowed set.
        """
        if not self._contract.delegates_to or child_contract.name not in self._contract.delegates_to:
            raise ValueError(
                f"Contract '{self._contract.name}' does not declare "
                f"'{child_contract.name}' in delegates_to."
            )
        self._delegation_stack.append(child_contract)

    def pop_delegation(self) -> SkillContract | None:
        """Pop the current delegation, returning control to the parent."""
        if self._delegation_stack:
            return self._delegation_stack.pop()
        return None

    def increment_iteration(self) -> None:
        """Advance the iteration counter (call once per agent loop turn)."""
        self._iteration += 1

    def _effective_tool_ids(self) -> set[str] | None:
        """Compute the effective tool whitelist including any delegation merges."""
        base = self._contract.tool_ids
        if not self._delegation_stack:
            return base

        merged: set[str] = set(base) if base else set()
        for child in self._delegation_stack:
            child_tools = child.tool_ids
            if child_tools is None:
                return None
            merged |= child_tools
        return merged if merged else None

    def check_tool_call(self, tool_name: str, tool_args: dict[str, Any]) -> ToolRewrite:
        """Evaluate a proposed tool call against the contract.

        Returns a ToolRewrite indicating whether the call is allowed,
        rewritten (via overrides), or blocked.
        """
        resolved = self._contract.resolve_tool(tool_name)
        rewritten = resolved != tool_name

        effective_tools = self._effective_tool_ids()
        if effective_tools is not None and resolved not in effective_tools:
            return ToolRewrite(
                tool_name=resolved,
                tool_args=tool_args,
                rewritten=rewritten,
                blocked=True,
                block_reason=f"Tool '{resolved}' is not in tool_ids.",
            )

        return ToolRewrite(
            tool_name=resolved,
            tool_args=tool_args,
            rewritten=rewritten,
        )

    def evaluate(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tracker: EvidenceTracker,
        *,
        step_index: int | None = None,
        mode: EnforcementMode | None = None,
    ) -> ToolDecision:
        """Check one proposed tool call against every contract rule and apply the enforcement mode.

        Rules, first violation wins: ``tool_ids``, plan step order, then the step's
        ``requires_evidence`` gate. Pass ``step_index`` when the host runs the plan itself and
        knows which step the call is for: the order check is skipped and that step's gate is
        used. Without it, the step is inferred from ``current_step_index``, as for an agent
        choosing its own tools. ``mode`` overrides the contract's ``enforcement``.
        """
        rewrite = self.check_tool_call(tool_name, tool_args)
        reason = rewrite.block_reason if rewrite.blocked else None
        if reason is None and step_index is None:
            reason = self._step_order_violation(rewrite.tool_name)
        if reason is None:
            reason = self._evidence_gate_violation(rewrite.tool_name, tracker, step_index)

        effective = mode or self._contract.enforcement_mode
        action: ToolAction
        if reason is None or effective is EnforcementMode.off:
            action = "allow"
        elif effective is EnforcementMode.soft:
            action = "warn"
        else:
            action = "block"
        return ToolDecision(
            tool_name=rewrite.tool_name,
            tool_args=rewrite.tool_args,
            action=action,
            reason=reason,
            rewritten=rewrite.rewritten,
        )

    def advance(self, tool_name: str) -> int | None:
        """Complete the current plan step if ``tool_name`` resolves to its tool. Returns its index, else None."""
        tool_name = self._contract.resolve_tool(tool_name)
        steps = self._contract.plan_steps
        index = self._step_index
        if index >= len(steps) or steps[index].tool != tool_name:
            return None
        self._completed_steps.add(index)
        self._step_index += 1
        return index

    def _step_order_violation(self, tool_name: str) -> str | None:
        """A tool from a later plan step is blocked until the current step has run.

        Retrying a past step, and tools that are in no plan step, are always allowed.
        """
        steps = self._contract.plan_steps
        matching = [i for i, step in enumerate(steps) if step.tool == tool_name]
        current = self._step_index
        if not matching or any(i <= current or i in self._completed_steps for i in matching):
            return None
        earliest = min(i for i in matching if i > current)
        current_tool = steps[current].tool if current < len(steps) else "unknown"
        return f"Step {current + 1} ({current_tool}) must complete before step {earliest + 1} ({tool_name})."

    def _evidence_gate_violation(
        self, tool_name: str, tracker: EvidenceTracker, step_index: int | None
    ) -> str | None:
        steps = self._contract.plan_steps
        if step_index is None:
            current = self._step_index
            if current >= len(steps) or steps[current].tool != tool_name:
                return None
            step_index = current
        step = steps[step_index]
        missing = [eid for eid in step.requires_evidence or [] if eid not in tracker.collected_ids]
        if not missing:
            return None
        return (
            f"Step {step_index + 1} ({step.tool}) requires evidence: {', '.join(missing)}. "
            "Collect the missing evidence first."
        )

    def can_finalize(self, tracker: EvidenceTracker) -> bool:
        """Check whether the agent is permitted to finalize.

        Considers:
        - min_iterations from finalization rules
        - require_all_evidence flag
        """
        fin = self._contract.finalization

        if self._iteration < fin.min_iterations:
            return False

        if fin.require_all_evidence and tracker.has_gaps:
            return False

        return True

    def finalization_blockers(self, tracker: EvidenceTracker) -> list[str]:
        """Return human-readable reasons preventing finalization."""
        blockers: list[str] = []
        fin = self._contract.finalization

        if self._iteration < fin.min_iterations:
            blockers.append(
                f"Min iterations not met: {self._iteration}/{fin.min_iterations}"
            )

        if fin.require_all_evidence:
            for gap in tracker.gaps:
                blockers.append(f"Missing evidence: {gap}")

        return blockers
