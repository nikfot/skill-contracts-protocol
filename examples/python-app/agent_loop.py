#!/usr/bin/env python3
"""Example: OpenSkills-enforced agent loop.

Demonstrates the full lifecycle:
  1. Load a skill contract from a YAML file
  2. Build a system prompt from the contract
  3. Execute plan steps with template interpolation
  4. Enforce tool gating and track evidence
  5. Gate finalization until all evidence is collected

Tool calls are simulated with mock responses. Replace
`simulate_tool_call()` with your real tool execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openskills import load_skill
from openskills.adapters.prompt import build_system_prompt
from openskills.runtime import EvidenceTracker, PlanExecutor, SkillEnforcer


def simulate_tool_call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Mock tool execution. Replace with real tool calls in production."""
    if tool == "kubectl_get" and "deployment" in str(args.get("resource", "")):
        return {
            "success": True,
            "evidence": ["rollout_status"],
            "data": {
                "status": {"readyReplicas": 3, "replicas": 3, "conditions": [{"type": "Available", "status": "True"}]}
            },
        }
    elif tool == "kubectl_get" and "pods" in str(args.get("resource", "")):
        return {
            "success": True,
            "evidence": ["pods_healthy"],
            "data": {
                "items": [
                    {"metadata": {"name": "app-abc12"}, "status": {"phase": "Running"}},
                    {"metadata": {"name": "app-def34"}, "status": {"phase": "Running"}},
                    {"metadata": {"name": "app-ghi56"}, "status": {"phase": "Running"}},
                ]
            },
        }
    elif tool == "run_es_query":
        return {
            "success": True,
            "evidence": ["error_rate_checked"],
            "data": {"error_count": 2, "total_requests": 15000, "error_rate": 0.013},
        }
    else:
        return {"success": False, "error": f"Unknown tool: {tool}"}


def main() -> None:
    skill_path = Path(__file__).parent / "skill.yaml"
    contract = load_skill(skill_path)

    print(f"Loaded skill: {contract.name}")
    print(f"  Description: {contract.description}")
    print(f"  Allowed tools: {contract.allowed_tools}")
    print(f"  Plan steps: {len(contract.plan_steps)}")
    print(f"  Required evidence: {[e.id for e in contract.required_evidence]}")
    print()

    # -- Step 1: Build system prompt for your LLM --------------------------
    prompt = build_system_prompt(contract)
    print("=== System Prompt (inject into LLM context) ===")
    print(prompt)
    print()

    # -- Step 2: Initialize runtime components ------------------------------
    enforcer = SkillEnforcer(contract)
    tracker = EvidenceTracker(contract)
    planner = PlanExecutor(
        contract,
        context={
            "deployment_name": "my-api",
            "namespace": "production",
            "app_label": "my-api",
            "start_time": "2026-05-16T07:00:00Z",
        },
    )

    # -- Step 3: Execute plan steps -----------------------------------------
    print("=== Executing Plan Steps ===")
    for step in planner:
        print(f"\nStep: {step.description}")
        print(f"  Tool: {step.tool}")
        print(f"  Args: {step.args}")

        # Enforce: is this tool allowed?
        check = enforcer.check_tool_call(step.tool, step.args)
        if check.blocked:
            print(f"  BLOCKED: {check.block_reason}")
            continue
        if check.rewritten:
            print(f"  Rewritten to: {check.tool_name}")

        # Execute the tool (mock)
        result = simulate_tool_call(check.tool_name, step.args)
        print(f"  Result: success={result.get('success')}")

        # Record evidence from the result
        evidence_ids = result.get("evidence", [])
        if evidence_ids:
            tracker.record_many(evidence_ids)
            print(f"  Evidence collected: {evidence_ids}")

        enforcer.increment_iteration()

    # -- Step 4: Check finalization -----------------------------------------
    print("\n=== Finalization Check ===")
    print(f"Evidence collected: {tracker.collected_ids}")
    print(f"Evidence gaps: {tracker.gaps}")

    if enforcer.can_finalize(tracker):
        print("\nAll conditions met -- agent may finalize.")
        print("Generating final report...")
    else:
        blockers = enforcer.finalization_blockers(tracker)
        print("\nCannot finalize yet. Blockers:")
        for b in blockers:
            print(f"  - {b}")

    # -- Step 5: Demonstrate blocked tool call ------------------------------
    print("\n=== Demonstrating Tool Gating ===")
    rogue_check = enforcer.check_tool_call("delete_deployment", {"name": "my-api"})
    print(f"Attempting 'delete_deployment': blocked={rogue_check.blocked}")
    if rogue_check.block_reason:
        print(f"  Reason: {rogue_check.block_reason}")

    # -- Step 6: Demonstrate tool override ----------------------------------
    print("\n=== Demonstrating Tool Override ===")
    override_check = enforcer.check_tool_call("k8s_query", {"resource": "nodes"})
    print(f"Calling 'k8s_query': rewritten={override_check.rewritten}, resolved to '{override_check.tool_name}'")


if __name__ == "__main__":
    main()
