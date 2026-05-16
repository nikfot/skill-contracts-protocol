"""Referential integrity and semantic validation for OpenSkills contracts."""

from __future__ import annotations

from .models import SkillContract


def validate_contract(contract: SkillContract) -> list[str]:
    """Run referential integrity checks on a parsed SkillContract.

    Returns a list of error messages. Empty list means valid.

    Checks performed:
    1. Plan step tools must appear in allowed_tools (if defined).
    2. Tool override targets must appear in allowed_tools (if defined).
    3. Evidence IDs must be unique (also enforced by Pydantic, but checked
       here for completeness when consuming pre-validated data).
    """
    errors: list[str] = []
    allowed = contract.allowed_tools

    if allowed is not None:
        for i, step in enumerate(contract.plan_steps):
            if step.tool not in allowed:
                errors.append(
                    f"plan[{i}].tool '{step.tool}' is not in allowed_tools: {sorted(allowed)}"
                )

        for alias, target in contract.tool_overrides.items():
            if target not in allowed:
                errors.append(
                    f"tool_overrides['{alias}'] -> '{target}' is not in allowed_tools: {sorted(allowed)}"
                )

    seen_evidence_ids: set[str] = set()
    for item in contract.required_evidence:
        if item.id in seen_evidence_ids:
            errors.append(f"Duplicate evidence ID: '{item.id}'")
        seen_evidence_ids.add(item.id)

    return errors
