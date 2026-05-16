"""Elastic Agent Builder adapter.

Convert between OpenSkills contracts and the Elastic Agent Builder
Skills API (``POST /api/agent_builder/skills``) JSON payloads.

Two integration modes:

* **Prompt-injection** (``to_elastic_payload``): serialises the contract's
  constraints into structured Markdown prepended to the skill ``content``.
  No sidecar runtime needed -- the LLM self-enforces via prompt.

* **Runtime** (import the contract in your own agent loop and wrap it with
  ``SkillEnforcer`` / ``EvidenceTracker`` as usual).
"""

from __future__ import annotations

from typing import Any

from ..models import (
    Constraints,
    SkillContract,
)
from .prompt import build_system_prompt


def to_elastic_payload(
    contract: SkillContract,
    *,
    inject_constraints: bool = True,
) -> dict[str, Any]:
    """Convert a ``SkillContract`` to an Elastic Agent Builder API payload.

    Args:
        contract: A parsed OpenSkills skill contract.
        inject_constraints: If ``True``, prepend a structured enforcement
            preamble (tool guardrails, evidence gates, finalization rules)
            to the ``content`` field so the LLM can self-enforce.

    Returns:
        A ``dict`` suitable for ``POST /api/agent_builder/skills``.
    """
    payload: dict[str, Any] = {
        "id": contract.name,
        "name": contract.name,
        "description": _build_description(contract),
        "content": _build_content(contract, inject_constraints),
    }

    tool_ids = _extract_tool_ids(contract)
    if tool_ids:
        payload["tool_ids"] = tool_ids

    return payload


def from_elastic_payload(
    payload: dict[str, Any],
    *,
    openskills_version: str = "1.0",
) -> SkillContract:
    """Parse an Elastic Agent Builder skill payload into a ``SkillContract``.

    The resulting contract uses the payload's ``tool_ids`` as
    ``allowed_tools`` and the ``content`` field as the Markdown body.
    Plan steps and evidence are not inferred from prose -- they must be
    added manually if enforcement is desired.

    Args:
        payload: A dict from ``GET /api/agent_builder/skills/{id}``.
        openskills_version: Spec version to stamp on the contract.

    Returns:
        A ``SkillContract`` with ``allowed_tools`` populated from
        ``tool_ids`` and the original ``content`` preserved.
    """
    tool_ids = payload.get("tool_ids") or []
    constraints: Constraints | None = None
    if tool_ids:
        constraints = Constraints(allowed_tools=list(tool_ids))

    return SkillContract(
        openskills=openskills_version,
        name=payload.get("id") or payload["name"],
        description=payload.get("description", ""),
        constraints=constraints,
        content=payload.get("content", ""),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_description(contract: SkillContract) -> str:
    """Build the ``description`` field, folding triggers into the text."""
    desc = contract.description
    if contract.triggers:
        trigger_str = ", ".join(contract.triggers)
        desc = f"{desc} Triggers: {trigger_str}."
    return desc[:1024]


def _build_content(contract: SkillContract, inject_constraints: bool) -> str:
    """Assemble the ``content`` field.

    If *inject_constraints* is true the enforcement preamble is prepended
    to the original Markdown body.
    """
    parts: list[str] = []

    if inject_constraints and contract.constraints is not None:
        preamble = build_system_prompt(contract, include_plan=True)
        parts.append(preamble)
        parts.append("")
        parts.append("---")
        parts.append("")

    if contract.content:
        parts.append(contract.content)

    return "\n".join(parts)


def _extract_tool_ids(contract: SkillContract) -> list[str]:
    """Collect tool IDs from ``allowed_tools``."""
    if contract.allowed_tools is None:
        return []
    return sorted(contract.allowed_tools)
