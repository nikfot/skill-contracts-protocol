"""Tests for openskills.runtime.evidence."""

from openskills.models import (
    Constraints,
    EvidenceItem,
    EvidenceRequirements,
    SkillContract,
)
from openskills.runtime.evidence import EvidenceTracker


def _make_contract(evidence_ids: list[str]) -> SkillContract:
    return SkillContract(
        openskills="1.0",
        name="test",
        description="Test.",
        constraints=Constraints(
            evidence=EvidenceRequirements(
                required=[EvidenceItem(id=eid, description=eid) for eid in evidence_ids]
            )
        ),
    )


class TestEvidenceTracker:
    def test_initial_state(self) -> None:
        contract = _make_contract(["a", "b", "c"])
        tracker = EvidenceTracker(contract)
        assert tracker.required_ids == {"a", "b", "c"}
        assert tracker.collected_ids == set()
        assert tracker.has_gaps
        assert not tracker.is_complete

    def test_record_single(self) -> None:
        contract = _make_contract(["a", "b"])
        tracker = EvidenceTracker(contract)
        tracker.record("a")
        assert "a" in tracker.collected_ids
        assert tracker.gap_ids == {"b"}

    def test_record_many(self) -> None:
        contract = _make_contract(["a", "b", "c"])
        tracker = EvidenceTracker(contract)
        tracker.record_many({"a", "c"})
        assert tracker.gap_ids == {"b"}

    def test_complete(self) -> None:
        contract = _make_contract(["a"])
        tracker = EvidenceTracker(contract)
        tracker.record("a")
        assert tracker.is_complete
        assert not tracker.has_gaps

    def test_gaps_preserves_order(self) -> None:
        contract = _make_contract(["first", "second", "third"])
        tracker = EvidenceTracker(contract)
        tracker.record("second")
        gaps = tracker.gaps
        assert gaps == ["first", "third"]

    def test_reset(self) -> None:
        contract = _make_contract(["a"])
        tracker = EvidenceTracker(contract)
        tracker.record("a")
        assert tracker.is_complete
        tracker.reset()
        assert tracker.has_gaps

    def test_no_requirements(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="open",
            description="No evidence needed.",
        )
        tracker = EvidenceTracker(contract)
        assert tracker.is_complete
        assert not tracker.has_gaps

    def test_extra_evidence_ignored(self) -> None:
        contract = _make_contract(["a"])
        tracker = EvidenceTracker(contract)
        tracker.record("a")
        tracker.record("unknown_extra")
        assert tracker.is_complete
        assert "unknown_extra" in tracker.collected_ids
