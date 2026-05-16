"""Elastic Agent Builder compatibility checks.

Validates that an SCP contract conforms to Elastic naming
conventions, API limits, and skill authoring guidelines.
"""

from __future__ import annotations

from .models import SkillContract

ELASTIC_TOOL_NAMESPACES = frozenset({
    "platform",
    "security",
    "observability",
})

ELASTIC_NAME_MAX = 64
ELASTIC_DESCRIPTION_MAX = 1024
ELASTIC_TOOL_IDS_MAX = 100


def validate_elastic_compatibility(contract: SkillContract) -> list[str]:
    """Check a contract against Elastic Agent Builder API limits and guidelines.

    Returns a list of warning/error strings. Empty means fully compatible.
    """
    issues: list[str] = []

    if len(contract.name) > ELASTIC_NAME_MAX:
        issues.append(
            f"Name exceeds Elastic's {ELASTIC_NAME_MAX}-char limit "
            f"({len(contract.name)} chars)."
        )

    if len(contract.description) > ELASTIC_DESCRIPTION_MAX:
        issues.append(
            f"Description exceeds Elastic's {ELASTIC_DESCRIPTION_MAX}-char limit "
            f"({len(contract.description)} chars)."
        )

    desc_lower = contract.description.lower()
    if "use when" not in desc_lower and "use this" not in desc_lower:
        issues.append(
            "Description should include a 'Use when...' clause per Elastic guidelines "
            "to help the agent route to this skill correctly."
        )

    if contract.tool_ids is not None:
        if len(contract.tool_ids) > ELASTIC_TOOL_IDS_MAX:
            issues.append(
                f"Tool list exceeds Elastic's {ELASTIC_TOOL_IDS_MAX}-tool limit "
                f"({len(contract.tool_ids)} tools)."
            )

    issues.extend(_check_tool_namespaces(contract))

    return issues


def _check_tool_namespaces(contract: SkillContract) -> list[str]:
    """Warn if dotted tool names use unknown Elastic namespace prefixes."""
    warnings: list[str] = []
    if contract.tool_ids is None:
        return warnings

    for tool in sorted(contract.tool_ids):
        if "." in tool:
            prefix = tool.split(".")[0]
            if prefix not in ELASTIC_TOOL_NAMESPACES:
                warnings.append(
                    f"Tool '{tool}' uses dotted notation but prefix "
                    f"'{prefix}' is not a known Elastic namespace "
                    f"({', '.join(sorted(ELASTIC_TOOL_NAMESPACES))})."
                )

    return warnings
