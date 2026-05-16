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
    - Gate tool calls against allowed_tools
    - Rewrite tool names via tool_overrides
    - Decide when the agent may finalize
    """

    def __init__(self, contract: SkillContract) -> None:
        self._contract = contract
        self._iteration = 0

    @property
    def contract(self) -> SkillContract:
        return self._contract

    @property
    def iteration(self) -> int:
        return self._iteration

    def increment_iteration(self) -> None:
        """Advance the iteration counter (call once per agent loop turn)."""
        self._iteration += 1

    def check_tool_call(self, tool_name: str, tool_args: dict[str, Any]) -> ToolRewrite:
        """Evaluate a proposed tool call against the contract.

        Returns a ToolRewrite indicating whether the call is allowed,
        rewritten (via overrides), or blocked.
        """
        resolved = self._contract.resolve_tool(tool_name)
        rewritten = resolved != tool_name

        if not self._contract.is_tool_allowed(resolved):
            return ToolRewrite(
                tool_name=resolved,
                tool_args=tool_args,
                rewritten=rewritten,
                blocked=True,
                block_reason=f"Tool '{resolved}' is not in allowed_tools.",
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
