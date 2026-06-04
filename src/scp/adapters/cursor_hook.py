"""Cursor IDE hook adapter for SCP enforcement.

Provides handler functions for Cursor's hook system (preToolUse, postToolUse,
sessionStart) that enforce SCP contracts deterministically at runtime.

State is persisted to a JSON file between hook invocations so the enforcer
can track collected evidence, delegation stack, and iteration count across
the entire agent session.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..loader import load_skill
from ..models import EvidenceDetectionRule, SkillContract
from ..runtime.enforcer import SkillEnforcer
from ..runtime.evidence import EvidenceTracker


@dataclass
class SessionState:
    """Serializable session state persisted between hook calls."""

    active_skill_path: str | None = None
    collected_evidence: list[str] = field(default_factory=list)
    delegation_stack: list[str] = field(default_factory=list)
    iteration: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_skill_path": self.active_skill_path,
            "collected_evidence": self.collected_evidence,
            "delegation_stack": self.delegation_stack,
            "iteration": self.iteration,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        return cls(
            active_skill_path=data.get("active_skill_path"),
            collected_evidence=data.get("collected_evidence", []),
            delegation_stack=data.get("delegation_stack", []),
            iteration=data.get("iteration", 0),
        )


def _state_path() -> Path:
    """Compute the path for session state persistence."""
    pid = os.getpid()
    return Path(tempfile.gettempdir()) / f"scp-session-{pid}.json"


def load_state() -> SessionState:
    """Load session state from disk, or return fresh state."""
    path = _state_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SessionState.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return SessionState()
    return SessionState()


def save_state(state: SessionState) -> None:
    """Persist session state to disk."""
    path = _state_path()
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


def _load_contract(skill_path: str) -> SkillContract | None:
    """Load a contract from a skill path, returning None on failure."""
    try:
        return load_skill(skill_path)
    except (ValueError, FileNotFoundError, OSError):
        return None


def _build_enforcer(state: SessionState) -> tuple[SkillContract, SkillEnforcer, EvidenceTracker] | None:
    """Reconstruct enforcer and tracker from persisted state."""
    if not state.active_skill_path:
        return None

    contract = _load_contract(state.active_skill_path)
    if contract is None:
        return None

    enforcer = SkillEnforcer(contract)
    enforcer._iteration = state.iteration

    for child_path in state.delegation_stack:
        child = _load_contract(child_path)
        if child:
            enforcer.push_delegation(child)

    tracker = EvidenceTracker(contract)
    tracker.record_many(state.collected_evidence)

    return contract, enforcer, tracker


def _check_evidence_detection(
    contract: SkillContract,
    tool_name: str,
    result_str: str,
) -> list[str]:
    """Check detection rules and return list of evidence IDs satisfied."""
    if not contract.constraints or not contract.constraints.evidence:
        return []
    rules = contract.constraints.evidence.detection
    if not rules:
        return []

    satisfied: list[str] = []
    for rule in rules:
        if not re.search(rule.tool_pattern, tool_name):
            continue
        if rule.result_pattern is None:
            satisfied.append(rule.evidence_id)
        elif re.search(rule.result_pattern, result_str):
            satisfied.append(rule.evidence_id)

    return satisfied


def handle_session_start(stdin_json: dict[str, Any]) -> dict[str, Any]:
    """Handle sessionStart hook -- detect active skill from initial prompt.

    Cursor passes the initial user message. We scan for skill activation
    triggers (slash commands or keyword matches) to determine which
    contract to enforce.

    Returns: {"decision": "approve"} (session start is never blocked).
    """
    state = SessionState()

    user_message = stdin_json.get("userMessage", "")
    skill_path = _detect_skill_from_message(user_message)

    if skill_path:
        state.active_skill_path = skill_path

    save_state(state)
    return {"decision": "approve"}


def handle_pre_tool_use(stdin_json: dict[str, Any]) -> dict[str, Any]:
    """Handle preToolUse hook -- gate tool calls against the active contract.

    Returns:
        {"decision": "approve"} if the tool is allowed.
        {"decision": "reject", "reason": "..."} if blocked.
    """
    state = load_state()
    result = _build_enforcer(state)

    if result is None:
        return {"decision": "approve"}

    contract, enforcer, tracker = result

    tool_name = stdin_json.get("toolName", "")
    tool_args = stdin_json.get("toolArgs", {})

    rewrite = enforcer.check_tool_call(tool_name, tool_args)

    if rewrite.blocked:
        return {
            "decision": "reject",
            "reason": rewrite.block_reason or f"Tool '{tool_name}' not allowed by SCP contract.",
        }

    return {"decision": "approve"}


def handle_post_tool_use(stdin_json: dict[str, Any]) -> dict[str, Any]:
    """Handle postToolUse hook -- detect evidence from tool results.

    Scans the tool result against detection rules and records any
    matched evidence items.

    Returns: {"decision": "approve"} (post-tool is never blocking).
    """
    state = load_state()
    result = _build_enforcer(state)

    if result is None:
        return {"decision": "approve"}

    contract, enforcer, tracker = result

    tool_name = stdin_json.get("toolName", "")
    tool_result = stdin_json.get("toolResult", "")
    result_str = str(tool_result) if not isinstance(tool_result, str) else tool_result

    satisfied = _check_evidence_detection(contract, tool_name, result_str)
    if satisfied:
        for eid in satisfied:
            if eid not in state.collected_evidence:
                state.collected_evidence.append(eid)
        save_state(state)

    return {"decision": "approve"}


def _detect_skill_from_message(message: str) -> str | None:
    """Detect which skill contract to activate from a user message.

    Strategy:
    1. Look for /slash-command patterns and map to known skill paths.
    2. Also match /<skill-name> (the name field from the contract).
    3. Scan SCP_SKILL_DIRS for SKILL.md files with matching triggers.

    Returns the path to the SKILL.md file, or None.
    """
    skill_dirs = os.environ.get("SCP_SKILL_DIRS", "")
    if not skill_dirs:
        return None

    paths = [Path(d.strip()) for d in skill_dirs.split(":") if d.strip()]
    msg_stripped = message.strip()

    for skill_dir in paths:
        if not skill_dir.is_dir():
            continue
        for skill_file in skill_dir.rglob("SKILL.md"):
            try:
                contract = load_skill(skill_file)
            except (ValueError, OSError):
                continue

            if contract.activation and contract.activation.slash_command:
                cmd = contract.activation.slash_command
                if msg_stripped.startswith(cmd):
                    return str(skill_file)

            if msg_stripped.startswith(f"/{contract.name}"):
                return str(skill_file)

            for trigger in contract.effective_triggers:
                if trigger.lower() in message.lower():
                    return str(skill_file)

    return None
