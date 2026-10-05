"""EvidenceTracker -- collect and check evidence against requirements.

Extracted and generalized from elastic/sophia's evidence.py. The Sophia
version had hard-coded column-name classifiers for proxy latency data.
This version is generic: callers explicitly record evidence IDs.
"""

from __future__ import annotations

import re

from ..models import SkillContract


class EvidenceTracker:
    """Track collected evidence against a contract's requirements.

    Usage:
        tracker = EvidenceTracker(contract)
        tracker.record("data_presence")
        tracker.record_many(tracker.detect("run_query", result_text))
        print(tracker.gaps)  # remaining unmet evidence IDs
    """

    def __init__(self, contract: SkillContract) -> None:
        self._required = {item.id: item.description for item in contract.required_evidence}
        self._collected: set[str] = set()
        evidence = contract.constraints.evidence if contract.constraints else None
        self._detection = list(evidence.detection or []) if evidence else []

    @property
    def required_ids(self) -> set[str]:
        """All required evidence IDs."""
        return set(self._required.keys())

    @property
    def collected_ids(self) -> set[str]:
        """Evidence IDs collected so far."""
        return set(self._collected)

    @property
    def gaps(self) -> list[str]:
        """Descriptions of missing evidence, in definition order."""
        return [
            desc for eid, desc in self._required.items()
            if eid not in self._collected
        ]

    @property
    def gap_ids(self) -> set[str]:
        """IDs of missing evidence."""
        return self.required_ids - self._collected

    @property
    def has_gaps(self) -> bool:
        """True if any required evidence is still missing."""
        return bool(self.gap_ids)

    @property
    def is_complete(self) -> bool:
        """True if all required evidence has been collected."""
        return not self.has_gaps

    def record(self, evidence_id: str) -> None:
        """Mark an evidence item as collected."""
        self._collected.add(evidence_id)

    def record_many(self, evidence_ids: set[str] | list[str]) -> None:
        """Mark multiple evidence items as collected."""
        self._collected.update(evidence_ids)

    def detect(self, tool_name: str, result_text: str) -> list[str]:
        """Return the evidence IDs the contract's detection rules match for one tool result.

        A rule matches when ``tool_pattern`` is found in ``tool_name`` and, if set,
        ``result_pattern`` is found in ``result_text``. Nothing is recorded; pass the
        result to ``record_many``. IDs are returned once each, in rule order.
        """
        matched: list[str] = []
        for rule in self._detection:
            if rule.evidence_id in matched or not re.search(rule.tool_pattern, tool_name):
                continue
            if rule.result_pattern is None or re.search(rule.result_pattern, result_text):
                matched.append(rule.evidence_id)
        return matched

    def reset(self) -> None:
        """Clear all collected evidence."""
        self._collected.clear()
