"""SkillEnforcer -- tool gating, rewriting, and finalization control.

Extracted and generalized from elastic/sophia's DefaultRuntime and
InvestigatorAgent loop.
"""

from __future__ import annotations

from typing import Any

from ..models import SkillContract
from .evidence import EvidenceTracker
from .protocol import ToolRewrite


class SkillEnforcer:
    """Enforces a SkillContract at runtime.

    Responsibilities:
    - Gate tool calls against tool_ids
    - Rewrite tool names via tool_overrides
    - Decide when the agent may finalize
    - Support contract stacking for delegation
    """

    def __init__(self, contract: SkillContract) -> None:
        self._contract = contract
        self._iteration = 0
        self._delegation_stack: list[SkillContract] = []

    @property
    def contract(self) -> SkillContract:
        return self._contract

    @property
    def iteration(self) -> int:
        return self._iteration

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
        if self._contract.delegates_to and child_contract.name not in self._contract.delegates_to:
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
        if effective_tools is not None and resolved not in effective_tools and tool_name not in effective_tools:
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
