"""Build structured system-prompt directives from a SkillContract.

This module produces plain text suitable for injection into any LLM's
system prompt. No LLM SDK dependency -- just strings.
"""

from __future__ import annotations

from ..models import SkillContract


def build_system_prompt(contract: SkillContract, include_plan: bool = True) -> str:
    """Generate system-prompt directives from a SkillContract.

    The output is a structured text block that can be appended to any
    LLM system prompt to enforce the contract's constraints.

    Args:
        contract: A parsed SkillContract.
        include_plan: If True, include the plan steps in the prompt.

    Returns:
        A multi-line string with structured directives.
    """
    sections: list[str] = []

    sections.append(f"## Skill: {contract.name}")
    sections.append(f"**Description:** {contract.description}")

    if contract.constraints is None:
        sections.append("\n*No constraints defined -- operate freely.*")
        return "\n".join(sections)

    sections.append("")

    if contract.allowed_tools is not None:
        tools_str = ", ".join(sorted(contract.allowed_tools))
        sections.append(f"### Allowed Tools\nYou may ONLY use these tools: {tools_str}")
        sections.append("Any tool call not in this list must be rejected.")
        sections.append("")

    if contract.tool_overrides:
        overrides_lines = [f"- `{alias}` -> `{target}`" for alias, target in contract.tool_overrides.items()]
        sections.append("### Tool Aliases")
        sections.append("If you intend to call these legacy names, use the mapped tool instead:")
        sections.extend(overrides_lines)
        sections.append("")

    if include_plan and contract.plan_steps:
        sections.append("### Investigation Plan")
        sections.append("Execute these steps IN ORDER before free-form investigation:")
        for i, step in enumerate(contract.plan_steps, 1):
            line = f"{i}. **{step.tool}**: {step.description}"
            if step.args_template:
                line += f" (args: `{step.args_template}`)"
            sections.append(line)
        sections.append("")

    if contract.required_evidence:
        sections.append("### Required Evidence")
        sections.append("You MUST collect ALL of the following before finalizing:")
        for item in contract.required_evidence:
            sections.append(f"- **{item.id}**: {item.description}")
        sections.append("")

    fin = contract.finalization
    finalization_lines: list[str] = []
    if fin.min_iterations > 0:
        finalization_lines.append(f"- Complete at least **{fin.min_iterations}** tool-call iterations.")
    if fin.require_all_evidence:
        finalization_lines.append("- ALL required evidence must be collected.")
    finalization_lines.append("- Do NOT finalize until all conditions above are met.")

    sections.append("### Finalization Rules")
    sections.extend(finalization_lines)

    return "\n".join(sections)
