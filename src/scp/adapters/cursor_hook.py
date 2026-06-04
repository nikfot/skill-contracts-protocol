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
import re
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


def _find_step_for_tool(contract: SkillContract, tool_name: str) -> list[int]:
    """Find all plan step indices whose tool matches the given tool name."""
    matches = []
    for i, step in enumerate(contract.plan_steps):
        if step.tool == tool_name:
            matches.append(i)
    return matches


def _check_step_order(
    contract: SkillContract,
    state: SessionState,
    tool_name: str,
) -> tuple[bool, str]:
    """Check if a tool call respects plan step ordering.

    Returns (allowed, reason). When allowed is False, reason explains why.

    Logic:
    - If tool matches current step: allowed (will advance)
    - If tool matches a past (completed) step: allowed (retries OK)
    - If tool matches a future step: blocked (must complete current first)
    - If tool is not in any plan step: allowed (utility tool)
    """
    plan_steps = contract.plan_steps
    if not plan_steps:
        return True, ""

    matching_indices = _find_step_for_tool(contract, tool_name)

    if not matching_indices:
        return True, ""

    current_idx = state.current_step_index

    for idx in matching_indices:
        if idx == current_idx:
            return True, ""
        if idx < current_idx or idx in state.completed_steps:
            return True, ""

    earliest_future = min(i for i in matching_indices if i > current_idx)
    current_step = plan_steps[current_idx] if current_idx < len(plan_steps) else None
    current_tool = current_step.tool if current_step else "unknown"

    return (
        False,
        f"Step {current_idx + 1} ({current_tool}) must complete before "
        f"step {earliest_future + 1} ({tool_name}).",
    )


def _check_evidence_gate(
    contract: SkillContract,
    state: SessionState,
    tool_name: str,
) -> tuple[bool, str]:
    """Check if the step's requires_evidence gate is satisfied.

    Returns (allowed, reason).
    """
    plan_steps = contract.plan_steps
    if not plan_steps:
        return True, ""

    matching_indices = _find_step_for_tool(contract, tool_name)
    if not matching_indices:
        return True, ""

    current_idx = state.current_step_index
    for idx in matching_indices:
        if idx != current_idx:
            continue
        step = plan_steps[idx]
        if not step.requires_evidence:
            return True, ""

        missing = [eid for eid in step.requires_evidence if eid not in state.collected_evidence]
        if missing:
            return (
                False,
                f"Step {idx + 1} ({tool_name}) requires evidence: {', '.join(missing)}. "
                f"Collect the missing evidence first.",
            )
        return True, ""

    return True, ""


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
    """Handle preToolUse hook -- enforce tool whitelist, step ordering, and evidence gates.

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

    # 1. Tool whitelist check
    rewrite = enforcer.check_tool_call(tool_name, tool_args)
    if rewrite.blocked:
        reason = rewrite.block_reason or f"Tool '{tool_name}' not in tool_ids."
        if mode == EnforcementMode.soft:
            logger.warning(f"[SCP soft] {reason}")
            return {"decision": "approve"}
        return {"decision": "reject", "reason": reason}

    # 2. Step order check
    allowed, reason = _check_step_order(contract, state, tool_name)
    if not allowed:
        if mode == EnforcementMode.soft:
            logger.warning(f"[SCP soft] {reason}")
            return {"decision": "approve"}
        return {"decision": "reject", "reason": reason}

    # 3. Evidence gate check
    allowed, reason = _check_evidence_gate(contract, state, tool_name)
    if not allowed:
        if mode == EnforcementMode.soft:
            logger.warning(f"[SCP soft] {reason}")
            return {"decision": "approve"}
        return {"decision": "reject", "reason": reason}

    # 4. Advance step index if this tool matches the current step
    plan_steps = contract.plan_steps
    if plan_steps and state.current_step_index < len(plan_steps):
        current_step = plan_steps[state.current_step_index]
        if current_step.tool == tool_name:
            _maybe_push_delegation(contract, state, state.current_step_index)
            state.completed_steps.append(state.current_step_index)
            state.current_step_index += 1
            _maybe_pop_delegation(contract, state, tool_name)
            save_state(state)

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
