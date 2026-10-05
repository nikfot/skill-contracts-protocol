"""Cursor IDE hook adapter for SCP enforcement.

Provides handler functions for Cursor's hook system (preToolUse, postToolUse,
sessionStart) that enforce SCP contracts deterministically at runtime.

Enforcement covers:
- Tool whitelist gating (tool_ids)
- Plan step ordering (must call step N's tool before step N+1)
- Evidence-gated steps (requires_evidence blocks tool until evidence collected)
- Delegation auto-activation (push/pop child contracts at delegates steps)
- Configurable modes: strict (reject), soft (warn + approve), off (pass-through)

State is persisted to a JSON file between hook invocations so the enforcer
can track collected evidence, delegation stack, step progress, and iteration
count across the entire agent session.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..loader import load_skill
from ..models import EnforcementMode, SkillContract
from ..runtime.enforcer import SkillEnforcer
from ..runtime.evidence import EvidenceTracker

logger = logging.getLogger("scp.hooks")


@dataclass
class SessionState:
    """Serializable session state persisted between hook calls."""

    active_skill_path: str | None = None
    collected_evidence: list[str] = field(default_factory=list)
    delegation_stack: list[str] = field(default_factory=list)
    current_step_index: int = 0
    completed_steps: list[int] = field(default_factory=list)
    iteration: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_skill_path": self.active_skill_path,
            "collected_evidence": self.collected_evidence,
            "delegation_stack": self.delegation_stack,
            "current_step_index": self.current_step_index,
            "completed_steps": self.completed_steps,
            "iteration": self.iteration,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        return cls(
            active_skill_path=data.get("active_skill_path"),
            collected_evidence=data.get("collected_evidence", []),
            delegation_stack=data.get("delegation_stack", []),
            current_step_index=data.get("current_step_index", 0),
            completed_steps=data.get("completed_steps", []),
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


def _resolve_enforcement_mode(contract: SkillContract) -> EnforcementMode:
    """Resolve effective enforcement mode: env var overrides contract."""
    env_mode = os.environ.get("SCP_MODE", "").strip().lower()
    if env_mode in ("strict", "soft", "off"):
        return EnforcementMode(env_mode)
    return contract.enforcement_mode


def _build_enforcer(state: SessionState) -> tuple[SkillContract, SkillEnforcer, EvidenceTracker] | None:
    """Reconstruct enforcer and tracker from persisted state."""
    if not state.active_skill_path:
        return None

    contract = _load_contract(state.active_skill_path)
    if contract is None:
        return None

    enforcer = SkillEnforcer(contract)
    enforcer.restore_progress(
        iteration=state.iteration,
        current_step_index=state.current_step_index,
        completed_steps=state.completed_steps,
    )

    for child_path in state.delegation_stack:
        child = _load_contract(child_path)
        if child:
            enforcer.push_delegation(child)

    tracker = EvidenceTracker(contract)
    tracker.record_many(state.collected_evidence)

    return contract, enforcer, tracker


def _maybe_push_delegation(
    contract: SkillContract,
    state: SessionState,
    step_index: int,
) -> None:
    """Push delegation if the current step declares delegates."""
    plan_steps = contract.plan_steps
    if step_index >= len(plan_steps):
        return

    step = plan_steps[step_index]
    if not step.delegates:
        return

    child_path = _find_skill_path(step.delegates)
    if child_path and child_path not in state.delegation_stack:
        state.delegation_stack.append(child_path)


def _maybe_pop_delegation(
    contract: SkillContract,
    state: SessionState,
    tool_name: str,
) -> None:
    """Pop delegation if we've moved past the delegates step to a parent step."""
    if not state.delegation_stack:
        return

    plan_steps = contract.plan_steps
    current_idx = state.current_step_index
    if current_idx >= len(plan_steps):
        return

    current_step = plan_steps[current_idx]
    if current_step.tool == tool_name and not current_step.delegates:
        if state.delegation_stack:
            state.delegation_stack.pop()


def _find_skill_path(skill_name: str) -> str | None:
    """Find a SKILL.md path by skill name in SCP_SKILL_DIRS."""
    skill_dirs = os.environ.get("SCP_SKILL_DIRS", "")
    if not skill_dirs:
        return None

    paths = [Path(d.strip()) for d in skill_dirs.split(":") if d.strip()]
    for skill_dir in paths:
        if not skill_dir.is_dir():
            continue
        for skill_file in skill_dir.rglob("SKILL.md"):
            try:
                c = load_skill(skill_file)
                if c.name == skill_name:
                    return str(skill_file)
            except (ValueError, OSError):
                continue
    return None


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
    """Handle preToolUse hook -- enforce the contract via ``SkillEnforcer.evaluate``.

    Returns:
        {"decision": "approve"} if the tool is allowed.
        {"decision": "reject", "reason": "..."} if blocked (strict mode).
    """
    state = load_state()
    result = _build_enforcer(state)

    if result is None:
        return {"decision": "approve"}

    contract, enforcer, tracker = result
    mode = _resolve_enforcement_mode(contract)

    if mode == EnforcementMode.off:
        return {"decision": "approve"}

    tool_name = stdin_json.get("toolName", "")
    tool_args = stdin_json.get("toolArgs", {})

    decision = enforcer.evaluate(tool_name, tool_args, tracker, mode=mode)
    if decision.action == "block":
        return {"decision": "reject", "reason": decision.reason}
    if decision.action == "warn":
        logger.warning(f"[SCP soft] {decision.reason}")
        return {"decision": "approve"}

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

    resolved_tool_name = contract.resolve_tool(tool_name)
    satisfied = tracker.detect(resolved_tool_name, result_str)
    if satisfied:
        for eid in satisfied:
            if eid not in state.collected_evidence:
                state.collected_evidence.append(eid)

    step_index = enforcer.current_step_index
    if enforcer.advance(resolved_tool_name) is not None:
        _maybe_push_delegation(contract, state, step_index)
        state.completed_steps = enforcer.completed_steps
        state.current_step_index = enforcer.current_step_index
        _maybe_pop_delegation(contract, state, resolved_tool_name)

    if satisfied or state.current_step_index != step_index:
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
                c = load_skill(skill_file)
            except (ValueError, OSError):
                continue

            if c.activation and c.activation.slash_command:
                cmd = c.activation.slash_command
                if msg_stripped.startswith(cmd):
                    return str(skill_file)

            if msg_stripped.startswith(f"/{c.name}"):
                return str(skill_file)

            for trigger in c.effective_triggers:
                if trigger.lower() in message.lower():
                    return str(skill_file)

    return None
