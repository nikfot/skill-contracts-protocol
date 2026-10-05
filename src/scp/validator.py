"""Referential integrity and semantic validation for SCP contracts."""

from __future__ import annotations

import re

from .models import SkillContract


def validate_contract(contract: SkillContract) -> list[str]:
    """Run referential integrity checks on a parsed SkillContract.

    Returns a list of error messages. Empty list means valid.

    Checks performed:
    1. Plan step tools must appear in tool_ids (if defined).
    2. Tool override targets must appear in tool_ids (if defined).
    3. Evidence IDs must be unique (also enforced by Pydantic, but checked
       here for completeness when consuming pre-validated data).
    4. When ``inputs`` is declared: names are unique, patterns compile, and
       every ``args_template`` placeholder is declared.
    """
    errors: list[str] = []
    allowed = contract.tool_ids

    if allowed is not None:
        for i, step in enumerate(contract.plan_steps):
            if step.tool not in allowed:
                errors.append(
                    f"plan[{i}].tool '{step.tool}' is not in tool_ids: {sorted(allowed)}"
                )

        for alias, target in contract.tool_overrides.items():
            if target not in allowed:
                errors.append(
                    f"tool_overrides['{alias}'] -> '{target}' is not in tool_ids: {sorted(allowed)}"
                )

    seen_evidence_ids: set[str] = set()
    for item in contract.required_evidence:
        if item.id in seen_evidence_ids:
            errors.append(f"Duplicate evidence ID: '{item.id}'")
        seen_evidence_ids.add(item.id)

    seen_ref_names: set[str] = set()
    for ref in contract.referenced_content:
        if ref.name in seen_ref_names:
            errors.append(f"Duplicate referenced_content name: '{ref.name}'")
        seen_ref_names.add(ref.name)

    if contract.inputs is not None:
        names = [spec.name for spec in contract.inputs]
        for name in sorted({n for n in names if names.count(n) > 1}):
            errors.append(f"Duplicate input name: '{name}'")
        for spec in contract.inputs:
            if spec.pattern is None:
                continue
            try:
                re.compile(spec.pattern)
            except re.error as exc:
                errors.append(f"inputs['{spec.name}'].pattern is not a valid regex: {exc}")
        for name in contract.placeholders:
            if name not in names:
                errors.append(f"Placeholder '{{{{{name}}}}}' is not declared in inputs")

    return errors
