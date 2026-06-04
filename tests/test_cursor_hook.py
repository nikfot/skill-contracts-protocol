"""Tests for scp.adapters.cursor_hook."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scp.adapters.cursor_hook import (
    SessionState,
    _check_evidence_detection,
    _state_path,
    handle_post_tool_use,
    handle_pre_tool_use,
    handle_session_start,
    load_state,
    save_state,
)
from scp.models import (
    Constraints,
    EvidenceDetectionRule,
    EvidenceItem,
    EvidenceRequirements,
    SkillContract,
)
from scp.runtime.enforcer import SkillEnforcer


def _make_contract(**kwargs: object) -> SkillContract:
    defaults = {"scp": "1.0", "name": "test", "description": "Test skill."}
    return SkillContract(**{**defaults, **kwargs})  # type: ignore[arg-type]


class TestSessionState:
    def test_round_trip(self) -> None:
        state = SessionState(
            active_skill_path="/tmp/skill.md",
            collected_evidence=["ev1", "ev2"],
            delegation_stack=["/tmp/child.md"],
            iteration=3,
        )
        data = state.to_dict()
        restored = SessionState.from_dict(data)
        assert restored.active_skill_path == "/tmp/skill.md"
        assert restored.collected_evidence == ["ev1", "ev2"]
        assert restored.delegation_stack == ["/tmp/child.md"]
        assert restored.iteration == 3

    def test_from_empty_dict(self) -> None:
        state = SessionState.from_dict({})
        assert state.active_skill_path is None
        assert state.collected_evidence == []
        assert state.delegation_stack == []
        assert state.iteration == 0


class TestStatePersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        state_file = tmp_path / "scp-session-test.json"
        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            state = SessionState(
                active_skill_path="/skills/test/SKILL.md",
                collected_evidence=["thread_read"],
                iteration=1,
            )
            save_state(state)
            loaded = load_state()
            assert loaded.active_skill_path == "/skills/test/SKILL.md"
            assert loaded.collected_evidence == ["thread_read"]
            assert loaded.iteration == 1

    def test_load_missing_file(self, tmp_path: Path) -> None:
        state_file = tmp_path / "nonexistent.json"
        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            state = load_state()
            assert state.active_skill_path is None

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        state_file = tmp_path / "bad.json"
        state_file.write_text("not json at all", encoding="utf-8")
        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            state = load_state()
            assert state.active_skill_path is None


class TestEvidenceDetection:
    def test_tool_pattern_only(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                evidence=EvidenceRequirements(
                    required=[EvidenceItem(id="thread_read", description="Thread read")],
                    detection=[
                        EvidenceDetectionRule(
                            evidence_id="thread_read",
                            tool_pattern=r"^slack_get_thread$",
                        )
                    ],
                )
            )
        )
        satisfied = _check_evidence_detection(contract, "slack_get_thread", "any result")
        assert "thread_read" in satisfied

    def test_tool_pattern_no_match(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                evidence=EvidenceRequirements(
                    required=[EvidenceItem(id="thread_read", description="Thread read")],
                    detection=[
                        EvidenceDetectionRule(
                            evidence_id="thread_read",
                            tool_pattern=r"^slack_get_thread$",
                        )
                    ],
                )
            )
        )
        satisfied = _check_evidence_detection(contract, "other_tool", "any result")
        assert satisfied == []

    def test_tool_and_result_pattern(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                evidence=EvidenceRequirements(
                    required=[EvidenceItem(id="alert_classified", description="Alert classified")],
                    detection=[
                        EvidenceDetectionRule(
                            evidence_id="alert_classified",
                            tool_pattern=r"^slack_get_thread$",
                            result_pattern=r"ecp-traffic",
                        )
                    ],
                )
            )
        )
        satisfied = _check_evidence_detection(
            contract, "slack_get_thread", '{"text": "ecp-traffic alert fired"}'
        )
        assert "alert_classified" in satisfied

    def test_result_pattern_no_match(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                evidence=EvidenceRequirements(
                    required=[EvidenceItem(id="alert_classified", description="Alert classified")],
                    detection=[
                        EvidenceDetectionRule(
                            evidence_id="alert_classified",
                            tool_pattern=r"^slack_get_thread$",
                            result_pattern=r"ecp-traffic",
                        )
                    ],
                )
            )
        )
        satisfied = _check_evidence_detection(
            contract, "slack_get_thread", '{"text": "unrelated message"}'
        )
        assert satisfied == []

    def test_no_detection_rules(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                evidence=EvidenceRequirements(
                    required=[EvidenceItem(id="ev", description="Evidence")]
                )
            )
        )
        satisfied = _check_evidence_detection(contract, "any_tool", "any result")
        assert satisfied == []

    def test_no_constraints(self) -> None:
        contract = _make_contract()
        satisfied = _check_evidence_detection(contract, "any_tool", "any result")
        assert satisfied == []


class TestDelegationStack:
    def test_push_and_pop(self) -> None:
        parent = _make_contract(
            constraints=Constraints(tool_ids=["slack_get_thread"]),
            delegates_to=["child-skill"],
        )
        child = _make_contract(
            name="child-skill",
            constraints=Constraints(tool_ids=["esql_query", "get_mappings"]),
        )
        enforcer = SkillEnforcer(parent)

        result = enforcer.check_tool_call("esql_query", {})
        assert result.blocked

        enforcer.push_delegation(child)
        result = enforcer.check_tool_call("esql_query", {})
        assert not result.blocked

        result = enforcer.check_tool_call("slack_get_thread", {})
        assert not result.blocked

        enforcer.pop_delegation()
        result = enforcer.check_tool_call("esql_query", {})
        assert result.blocked

    def test_push_undeclared_delegation_raises(self) -> None:
        parent = _make_contract(
            constraints=Constraints(tool_ids=["slack_get_thread"]),
            delegates_to=["allowed-child"],
        )
        child = _make_contract(
            name="other-child",
            constraints=Constraints(tool_ids=["esql_query"]),
        )
        enforcer = SkillEnforcer(parent)
        with pytest.raises(ValueError, match="does not declare"):
            enforcer.push_delegation(child)

    def test_nested_delegation(self) -> None:
        parent = _make_contract(
            constraints=Constraints(tool_ids=["tool_a"]),
            delegates_to=["child1", "child2"],
        )
        child1 = _make_contract(
            name="child1",
            constraints=Constraints(tool_ids=["tool_b"]),
        )
        child2 = _make_contract(
            name="child2",
            constraints=Constraints(tool_ids=["tool_c"]),
        )
        enforcer = SkillEnforcer(parent)
        enforcer.push_delegation(child1)
        enforcer.push_delegation(child2)

        assert not enforcer.check_tool_call("tool_a", {}).blocked
        assert not enforcer.check_tool_call("tool_b", {}).blocked
        assert not enforcer.check_tool_call("tool_c", {}).blocked
        assert enforcer.check_tool_call("tool_d", {}).blocked

    def test_unconstrained_child_allows_all(self) -> None:
        parent = _make_contract(
            constraints=Constraints(tool_ids=["tool_a"]),
            delegates_to=["child"],
        )
        child = _make_contract(name="child")
        enforcer = SkillEnforcer(parent)
        enforcer.push_delegation(child)

        assert not enforcer.check_tool_call("anything", {}).blocked


class TestHandlePreToolUse:
    def test_no_active_skill_allows_all(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            result = handle_pre_tool_use({"toolName": "anything", "toolArgs": {}})
            assert result["decision"] == "approve"

    def test_blocks_unauthorized_tool(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            "  tool_ids:\n"
            "    - allowed_tool\n"
            "---\n"
            "Body\n",
            encoding="utf-8",
        )

        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(skill_file))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            result = handle_pre_tool_use({"toolName": "forbidden_tool", "toolArgs": {}})
            assert result["decision"] == "reject"
            assert "reason" in result

    def test_allows_authorized_tool(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            "  tool_ids:\n"
            "    - allowed_tool\n"
            "---\n"
            "Body\n",
            encoding="utf-8",
        )

        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(skill_file))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            result = handle_pre_tool_use({"toolName": "allowed_tool", "toolArgs": {}})
            assert result["decision"] == "approve"


class TestHandlePostToolUse:
    def test_records_detected_evidence(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            "  evidence:\n"
            "    required:\n"
            "      - id: data_fetched\n"
            "        description: Data fetched\n"
            "    detection:\n"
            "      - evidence_id: data_fetched\n"
            "        tool_pattern: ^fetch_data$\n"
            "---\n"
            "Body\n",
            encoding="utf-8",
        )

        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(skill_file))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            result = handle_post_tool_use({
                "toolName": "fetch_data",
                "toolResult": "some data returned",
            })
            assert result["decision"] == "approve"

            updated_state = load_state()
            assert "data_fetched" in updated_state.collected_evidence

    def test_no_match_does_not_record(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            "  evidence:\n"
            "    required:\n"
            "      - id: data_fetched\n"
            "        description: Data fetched\n"
            "    detection:\n"
            "      - evidence_id: data_fetched\n"
            "        tool_pattern: ^fetch_data$\n"
            "---\n"
            "Body\n",
            encoding="utf-8",
        )

        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(skill_file))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            result = handle_post_tool_use({
                "toolName": "other_tool",
                "toolResult": "some data",
            })
            assert result["decision"] == "approve"

            updated_state = load_state()
            assert updated_state.collected_evidence == []


class TestHandleSessionStart:
    def test_detects_slash_command(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "activation:\n"
            "  slash_command: /test-skill\n"
            "constraints:\n"
            "  tool_ids:\n"
            "    - tool_a\n"
            "---\n"
            "Body\n",
            encoding="utf-8",
        )

        state_file = tmp_path / "state.json"
        with (
            patch("scp.adapters.cursor_hook._state_path", return_value=state_file),
            patch.dict(os.environ, {"SCP_SKILL_DIRS": str(skill_dir)}),
        ):
            result = handle_session_start({"userMessage": "/test-skill https://example.com"})
            assert result["decision"] == "approve"

            state = load_state()
            assert state.active_skill_path == str(skill_file)

    def test_no_match_passes_through(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        with (
            patch("scp.adapters.cursor_hook._state_path", return_value=state_file),
            patch.dict(os.environ, {"SCP_SKILL_DIRS": ""}),
        ):
            result = handle_session_start({"userMessage": "hello world"})
            assert result["decision"] == "approve"

            state = load_state()
            assert state.active_skill_path is None
