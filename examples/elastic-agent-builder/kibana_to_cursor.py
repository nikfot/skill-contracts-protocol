#!/usr/bin/env python3
"""Convert an Elastic Agent Builder skill into a Cursor IDE SKILL.md.

Demonstrates fetching (or simulating) a Kibana skill JSON payload and
writing it as an OpenSkills-compatible SKILL.md that Cursor can use.

Usage:
    python kibana_to_cursor.py                  # uses built-in example
    python kibana_to_cursor.py payload.json     # reads from file
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from openskills.adapters.elastic import from_elastic_payload

EXAMPLE_KIBANA_SKILL = {
    "id": "triage-security-alerts",
    "name": "Triage Security Alerts",
    "description": (
        "Triage and prioritize Elastic Security detection alerts. "
        "Use when a user asks to review, investigate, or summarize "
        "recent security alerts."
    ),
    "content": (
        "# Triage Security Alerts\n\n"
        "## Process\n\n"
        "1. Query recent detection alerts grouped by rule name\n"
        "2. Identify critical and high-severity alerts\n"
        "3. Check for correlated alerts across hosts or users\n"
        "4. Provide a prioritized summary with recommended actions\n\n"
        "## Edge Cases\n\n"
        "- **No alerts**: Confirm the detection rules are enabled "
        "and the time window is correct.\n"
        "- **Too many alerts**: Group by MITRE tactic first, then "
        "drill into specific rules.\n"
    ),
    "tool_ids": [
        "security.alerts",
        "platform.core.execute_esql",
        "platform.core.search",
    ],
    "referenced_content": [],
}


def main() -> None:
    if len(sys.argv) > 1:
        payload = json.loads(Path(sys.argv[1]).read_text())
    else:
        payload = EXAMPLE_KIBANA_SKILL
        print("# Using built-in example Kibana skill payload")
        print()

    contract = from_elastic_payload(payload)

    print("# Parsed as OpenSkills contract:")
    print(f"#   Name: {contract.name}")
    print(f"#   Description: {contract.description}")
    print(f"#   Allowed tools: {contract.allowed_tools}")
    print()

    data = contract.model_dump(exclude_none=True, exclude={"content"})
    fm = yaml.dump(data, default_flow_style=False, sort_keys=False).strip()
    body = contract.content or ""

    skill_md = f"---\n{fm}\n---\n\n{body}\n"

    output_path = Path(f".cursor/skills/{contract.name}/SKILL.md")
    print(f"# Output SKILL.md (would write to {output_path}):")
    print()
    print(skill_md)


if __name__ == "__main__":
    main()
