#!/usr/bin/env python3
"""Convert a Cursor IDE SKILL.md into an Elastic Agent Builder skill payload.

Demonstrates taking an OpenSkills-enhanced Cursor skill and producing the
JSON payload needed to deploy it as a Kibana Agent Builder skill.

Usage:
    python cursor_to_kibana.py ../../examples/cursor-ide/investigate-latency/SKILL.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from openskills import load_skill
from openskills.adapters.elastic import to_elastic_payload


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python cursor_to_kibana.py <path-to-cursor-skill.md>",
            file=sys.stderr,
        )
        sys.exit(1)

    skill_path = Path(sys.argv[1])
    contract = load_skill(skill_path)

    print(f"# Loaded Cursor skill: {contract.name}")
    print(f"#   Description: {contract.description}")
    print(f"#   Allowed tools: {contract.allowed_tools}")
    print(f"#   Plan steps: {len(contract.plan_steps)}")
    print(f"#   Evidence items: {len(contract.required_evidence)}")
    print()

    payload = to_elastic_payload(contract, inject_constraints=True)

    print("# Elastic Agent Builder API payload:")
    print("# POST /api/agent_builder/skills")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
