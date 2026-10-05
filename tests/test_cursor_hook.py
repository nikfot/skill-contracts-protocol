"""Tests for scp.adapters.cursor_hook."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scp.adapters.cursor_hook import (
    SessionState,
    handle_post_tool_use,
    handle_pre_tool_use,
    handle_session_start,
    load_state,
    save_state,
)
from scp.models import (
    Constraints,
    SkillContract,
)
from scp.runtime.enforcer import SkillEnforcer


def _make_contract(**kwargs: object) -> SkillContract:
    defaults = {"scp": "1.0", "name": "test", "description": "Test skill."}
    return SkillContract(**{**defaults, **kwargs})  # type: ignore[arg-type]


def _write_skill(tmp_path: Path, name: str = "test-skill", **extra: object) -> Path:
    """Write a SKILL.md file and return its path."""
    skill_file = tmp_path / f"{name}" / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)

    constraints = extra.pop("constraints_yaml", "")
    activation = extra.pop("activation_yaml", "")
    delegates_to = extra.pop("delegates_to_yaml", "")

    content = f"---\nscp: \"1.0\"\nname: {name}\ndescription: Test skill\n"
    if activation:
        content += f"{activation}\n"
    if delegates_to:
        content += f"{delegates_to}\n"
    if constraints:
        content += f"{constraints}\n"
    content += "---\nBody\n"

    skill_file.write_text(content, encoding="utf-8")
    return skill_file


class TestSessionState:
    def test_round_trip(self) -> None:
        state = SessionState(
            active_skill_path="/tmp/skill.md",
            collected_evidence=["ev1", "ev2"],
            delegation_stack=["/tmp/child.md"],
            current_step_index=2,
            completed_steps=[0, 1],
            iteration=3,
        )
        data = state.to_dict()
        restored = SessionState.from_dict(data)
        assert restored.active_skill_path == "/tmp/skill.md"
        assert restored.collected_evidence == ["ev1", "ev2"]
        assert restored.delegation_stack == ["/tmp/child.md"]
        assert restored.current_step_index == 2
        assert restored.completed_steps == [0, 1]
        assert restored.iteration == 3

    def test_from_empty_dict(self) -> None:
        state = SessionState.from_dict({})
        assert state.active_skill_path is None
        assert state.collected_evidence == []
        assert state.current_step_index == 0
        assert state.completed_steps == []


class TestStatePersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        state_file = tmp_path / "scp-session-test.json"
        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            state = SessionState(
                active_skill_path="/skills/test/SKILL.md",
                collected_evidence=["thread_read"],
                current_step_index=1,
                completed_steps=[0],
                iteration=1,
            )
            save_state(state)
            loaded = load_state()
            assert loaded.active_skill_path == "/skills/test/SKILL.md"
            assert loaded.collected_evidence == ["thread_read"]
            assert loaded.current_step_index == 1
            assert loaded.completed_steps == [0]

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


class TestEnforcementModes:
    def test_strict_rejects(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            "  enforcement: strict\n"
            "  tool_ids:\n"
            "    - allowed_tool\n"
            "---\nBody\n",
            encoding="utf-8",
        )
        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(skill_file))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            result = handle_pre_tool_use({"toolName": "forbidden_tool", "toolArgs": {}})
            assert result["decision"] == "reject"

    def test_soft_approves_with_warning(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            "  enforcement: soft\n"
            "  tool_ids:\n"
            "    - allowed_tool\n"
            "---\nBody\n",
            encoding="utf-8",
        )
        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(skill_file))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            result = handle_pre_tool_use({"toolName": "forbidden_tool", "toolArgs": {}})
            assert result["decision"] == "approve"

    def test_off_approves_everything(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            '  enforcement: "off"\n'
            "  tool_ids:\n"
            "    - allowed_tool\n"
            "---\nBody\n",
            encoding="utf-8",
        )
        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(skill_file))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            result = handle_pre_tool_use({"toolName": "forbidden_tool", "toolArgs": {}})
            assert result["decision"] == "approve"

    def test_env_var_overrides_contract(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            "  enforcement: strict\n"
            "  tool_ids:\n"
            "    - allowed_tool\n"
            "---\nBody\n",
            encoding="utf-8",
        )
        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(skill_file))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with (
            patch("scp.adapters.cursor_hook._state_path", return_value=state_file),
            patch.dict(os.environ, {"SCP_MODE": "off"}),
        ):
            result = handle_pre_tool_use({"toolName": "forbidden_tool", "toolArgs": {}})
            assert result["decision"] == "approve"


class TestStepAdvancement:
    def test_advances_only_after_tool_completion(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            "  tool_ids:\n"
            "    - step_a\n"
            "    - step_b\n"
            "  plan:\n"
            "    - tool: step_a\n"
            "      description: First\n"
            "    - tool: step_b\n"
            "      description: Second\n"
            "---\nBody\n",
            encoding="utf-8",
        )
        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(skill_file))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            result = handle_pre_tool_use({"toolName": "step_a", "toolArgs": {}})
            assert result["decision"] == "approve"

            updated = load_state()
            assert updated.current_step_index == 0
            assert updated.completed_steps == []

            result = handle_post_tool_use({"toolName": "step_a", "toolResult": "completed"})
            assert result["decision"] == "approve"

            updated = load_state()
            assert updated.current_step_index == 1
            assert 0 in updated.completed_steps

    def test_blocks_future_step(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            "  tool_ids:\n"
            "    - step_a\n"
            "    - step_b\n"
            "  plan:\n"
            "    - tool: step_a\n"
            "      description: First\n"
            "    - tool: step_b\n"
            "      description: Second\n"
            "---\nBody\n",
            encoding="utf-8",
        )
        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(skill_file))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            result = handle_pre_tool_use({"toolName": "step_b", "toolArgs": {}})
            assert result["decision"] == "reject"
            assert "step_a" in result["reason"]


class TestEvidenceGateIntegration:
    def test_blocks_until_evidence_collected(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            'scp: "1.0"\n'
            "name: test-skill\n"
            "description: Test\n"
            "constraints:\n"
            "  tool_ids:\n"
            "    - read_data\n"
            "    - post_result\n"
            "  plan:\n"
            "    - tool: read_data\n"
            "      description: Read\n"
            "    - tool: post_result\n"
            "      description: Post\n"
            "      requires_evidence:\n"
            "        - data_read\n"
            "  evidence:\n"
            "    required:\n"
            "      - id: data_read\n"
            "        description: Data was read\n"
            "    detection:\n"
            "      - evidence_id: data_read\n"
            "        tool_pattern: ^read_data$\n"
            "---\nBody\n",
            encoding="utf-8",
        )
        state_file = tmp_path / "state.json"
        state = SessionState(
            active_skill_path=str(skill_file),
            current_step_index=1,
            completed_steps=[0],
        )
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            # Blocked: evidence not yet collected
            result = handle_pre_tool_use({"toolName": "post_result", "toolArgs": {}})
            assert result["decision"] == "reject"
            assert "data_read" in result["reason"]

            # Simulate evidence collection
            state.collected_evidence.append("data_read")
            state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

            # Now allowed
            result = handle_pre_tool_use({"toolName": "post_result", "toolArgs": {}})
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
            "---\nBody\n",
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
            "---\nBody\n",
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


def _activate(tmp_path: Path, frontmatter_yaml: str) -> Path:
    """Write an active SKILL.md with extra frontmatter and return the session state file."""
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(
        f'---\nscp: "1.0"\nname: test-skill\ndescription: Test\n{frontmatter_yaml}---\nBody\n', encoding="utf-8"
    )
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(SessionState(active_skill_path=str(skill_file)).to_dict()), encoding="utf-8")
    return state_file


_INVALID = "constraints:\n  plan:\n    - tool: a\n      description: A\n      requires_evidence: [typo]\n"


class TestInvalidActiveContract:
    @pytest.mark.parametrize(
        ("mode", "decision"), [("", "reject"), ("strict", "reject"), ("soft", "approve"), ("off", "approve")]
    )
    def test_env_mode_decides(self, tmp_path: Path, mode: str, decision: str) -> None:
        state_file = _activate(tmp_path, _INVALID)

        with (
            patch("scp.adapters.cursor_hook._state_path", return_value=state_file),
            patch.dict(os.environ, {"SCP_MODE": mode}),
        ):
            result = handle_pre_tool_use({"toolName": "a", "toolArgs": {}})

        assert result["decision"] == decision
        if decision == "reject":
            assert "typo" in result["reason"]

    def test_missing_contract_file_rejects(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state = SessionState(active_skill_path=str(tmp_path / "gone" / "SKILL.md"))
        state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

        with (
            patch("scp.adapters.cursor_hook._state_path", return_value=state_file),
            patch.dict(os.environ, {"SCP_MODE": ""}),
        ):
            assert handle_pre_tool_use({"toolName": "a", "toolArgs": {}})["decision"] == "reject"

    def test_post_tool_use_records_nothing(self, tmp_path: Path) -> None:
        state_file = _activate(tmp_path, _INVALID)

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            assert handle_post_tool_use({"toolName": "a", "toolResult": ""}) == {"decision": "approve"}
            assert load_state().collected_evidence == []


_DELEGATING = (
    "delegates_to: [child-skill]\n"
    "constraints:\n  plan:\n"
    "    - tool: step_a\n      description: A\n      delegates: child-skill\n"
    "    - tool: step_b\n      description: B\n"
)


class TestDelegateResolution:
    def test_missing_delegate_rejects_in_strict(self, tmp_path: Path) -> None:
        state_file = _activate(tmp_path, _DELEGATING)

        with (
            patch("scp.adapters.cursor_hook._state_path", return_value=state_file),
            patch.dict(os.environ, {"SCP_MODE": "", "SCP_SKILL_DIRS": ""}),
        ):
            result = handle_pre_tool_use({"toolName": "step_a", "toolArgs": {}})

            assert result["decision"] == "reject"
            assert "child-skill" in result["reason"]
            assert load_state().current_step_index == 0

    def test_found_delegate_is_pushed(self, tmp_path: Path) -> None:
        state_file = _activate(tmp_path, _DELEGATING)
        skills = tmp_path / "skills"
        child = _write_skill(skills, "child-skill")

        with (
            patch("scp.adapters.cursor_hook._state_path", return_value=state_file),
            patch.dict(os.environ, {"SCP_MODE": "", "SCP_SKILL_DIRS": str(skills)}),
        ):
            result = handle_pre_tool_use({"toolName": "step_a", "toolArgs": {}})
            assert result["decision"] == "approve"
            assert load_state().delegation_stack == []

            handle_post_tool_use({"toolName": "step_a", "toolResult": "ok"})

            state = load_state()
            assert state.delegation_stack == [str(child)]
            assert state.current_step_index == 1


_ALIASED = (
    "constraints:\n  tool_ids: [fetch_data]\n  tool_overrides:\n    search: fetch_data\n"
    "  plan:\n    - tool: fetch_data\n      description: Fetch\n"
    "  evidence:\n    required:\n      - id: fetched\n        description: Fetched\n"
    "    detection:\n      - evidence_id: fetched\n        tool_pattern: ^fetch_data$\n"
)


class TestAliases:
    def test_alias_advances_the_plan(self, tmp_path: Path) -> None:
        state_file = _activate(tmp_path, _ALIASED)

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            assert handle_pre_tool_use({"toolName": "search", "toolArgs": {}})["decision"] == "approve"
            handle_post_tool_use({"toolName": "search", "toolResult": "rows"})
            assert load_state().current_step_index == 1

    def test_alias_result_is_detected_as_its_target(self, tmp_path: Path) -> None:
        state_file = _activate(tmp_path, _ALIASED)

        with patch("scp.adapters.cursor_hook._state_path", return_value=state_file):
            handle_post_tool_use({"toolName": "search", "toolResult": "rows"})
            assert load_state().collected_evidence == ["fetched"]
