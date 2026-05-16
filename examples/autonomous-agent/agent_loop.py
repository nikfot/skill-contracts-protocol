#!/usr/bin/env python3
"""Autonomous agent with SCP enforcement.

Demonstrates the pattern for agents that run without human supervision
(remote MCP servers, background workers, webhook handlers). The agent
keeps looping until the SCP contract is satisfied -- it cannot declare
itself done until all evidence is collected and finalization rules are met.

Usage:
    python agent_loop.py                          # mock tools
    python agent_loop.py --hostname my-node-01    # custom hostname
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from scp import load_skill
from scp.adapters.prompt import build_system_prompt
from scp.runtime import EvidenceTracker, PlanExecutor, SkillEnforcer


def simulate_tool_call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Mock tool execution. Replace with real tool calls in production.

    In a real autonomous agent, these would be:
    - HTTP calls to an Elasticsearch cluster
    - kubectl / Kubernetes API calls
    - SSH commands via Teleport
    - MCP tool invocations
    """
    if tool == "query_elasticsearch" and "metricbeat" in str(args.get("index", "")):
        return {
            "success": True,
            "evidence": ["node_resource_usage"],
            "data": {
                "cpu_percent": 92.3,
                "memory_percent": 87.1,
                "disk_percent": 71.4,
                "pressure_duration_minutes": 12,
            },
        }

    if tool == "check_pod_status":
        return {
            "success": True,
            "evidence": ["pod_health_summary"],
            "data": {
                "total_pods": 14,
                "running": 11,
                "crash_loop": 2,
                "evicted": 1,
                "affected_workloads": [
                    {"name": "api-server-7f8b9", "status": "CrashLoopBackOff", "restarts": 7},
                    {"name": "worker-batch-3c2a1", "status": "CrashLoopBackOff", "restarts": 4},
                    {"name": "cache-redis-0", "status": "Evicted", "restarts": 0},
                ],
            },
        }

    if tool == "get_system_logs":
        return {
            "success": True,
            "evidence": ["system_log_review"],
            "data": {
                "oom_kills": 3,
                "disk_errors": 0,
                "nic_flaps": 0,
                "notable_entries": [
                    "kernel: Out of memory: Killed process 14523 (java) total-vm:8234512kB",
                    "kernel: Out of memory: Killed process 14891 (python3) total-vm:4102344kB",
                    "kernel: Memory cgroup out of memory: Killed process 15002 (node)",
                ],
            },
        }

    if tool == "query_elasticsearch" and "logs-*" in str(args.get("index", "")):
        return {
            "success": True,
            "evidence": ["root_cause_hypothesis"],
            "data": {
                "oom_killed_pods": 3,
                "evicted_pods": 1,
                "timeline": "OOM kills started at 14:02, pod evictions at 14:05, node NotReady at 14:08",
                "hypothesis": (
                    "Memory pressure caused by api-server workload exceeding its "
                    "memory limit (8Gi requested, ~8.2Gi actual). Cascading OOM kills "
                    "affected co-located pods. Recommend increasing memory limit to 10Gi "
                    "or adding resource quotas."
                ),
            },
        }

    return {"success": False, "error": f"Unknown tool: {tool}"}


def run_autonomous_agent(hostname: str) -> None:
    """Run the autonomous investigation loop.

    This is the core pattern: load contract -> execute plan -> track
    evidence -> keep going until can_finalize() returns True.
    """
    skill_path = Path(__file__).parent / "skill.yaml"
    contract = load_skill(skill_path)

    print(f"=== Autonomous Agent: {contract.name} ===")
    print(f"Description: {contract.description}")
    print(f"Tool whitelist: {sorted(contract.tool_ids or [])}")
    print(f"Evidence required: {[e.id for e in contract.required_evidence]}")
    print(f"Min iterations: {contract.finalization.min_iterations}")
    print()

    enforcer = SkillEnforcer(contract)
    tracker = EvidenceTracker(contract)
    planner = PlanExecutor(
        contract,
        context={
            "hostname": hostname,
            "start_time": "2026-05-16T14:00:00Z",
        },
    )

    # The system prompt would be sent to the LLM in a real agent
    system_prompt = build_system_prompt(contract)
    print("--- System Prompt (sent to LLM) ---")
    print(system_prompt)
    print("--- End System Prompt ---\n")

    # Phase 1: Execute the deterministic plan
    print("=== Phase 1: Executing Plan ===\n")
    for step in planner:
        print(f"[PLAN] {step.description}")
        print(f"  Tool: {step.tool}")
        print(f"  Args: {step.args}")

        check = enforcer.check_tool_call(step.tool, step.args)
        if check.blocked:
            print(f"  BLOCKED: {check.block_reason}")
            continue

        result = simulate_tool_call(check.tool_name, step.args)
        print(f"  Result: success={result.get('success')}")

        for eid in result.get("evidence", []):
            tracker.record(eid)
            print(f"  Evidence collected: {eid}")

        enforcer.increment_iteration()

        # Check: can we finalize?
        if enforcer.can_finalize(tracker):
            print("\n  [CHECK] Can finalize: YES")
        else:
            blockers = enforcer.finalization_blockers(tracker)
            print("\n  [CHECK] Can finalize: NO")
            for b in blockers:
                print(f"    - {b}")
        print()

    # Phase 2: Free-form investigation (if plan didn't satisfy the contract)
    max_free_iterations = 5
    free_iteration = 0

    while not enforcer.can_finalize(tracker) and free_iteration < max_free_iterations:
        free_iteration += 1
        print(f"=== Phase 2: Free-form iteration {free_iteration} ===")
        gaps = tracker.gaps
        print(f"  Missing evidence: {gaps}")
        print("  (In a real agent, the LLM would decide what tool to call next)")
        print()
        enforcer.increment_iteration()

    # Final check
    print("=== Finalization ===\n")
    print(f"Evidence collected: {sorted(tracker.collected_ids)}")
    print(f"Evidence gaps: {tracker.gaps}")
    print(f"Total iterations: {enforcer.iteration}")

    if enforcer.can_finalize(tracker):
        print("\nAll contract conditions met. Agent may produce final report.")
        print("In production, the report goes back to PagerDuty / Slack / the caller.")
    else:
        blockers = enforcer.finalization_blockers(tracker)
        print("\nContract NOT satisfied. Remaining blockers:")
        for b in blockers:
            print(f"  - {b}")
        print("Agent would escalate to a human operator.")

    # Demonstrate that rogue tool calls are blocked
    print("\n=== Tool Gating Demo ===\n")
    for rogue_tool in ["delete_node", "kubectl_drain", "reboot_host"]:
        check = enforcer.check_tool_call(rogue_tool, {})
        print(f"  {rogue_tool}: {'BLOCKED' if check.blocked else 'allowed'}")
        if check.block_reason:
            print(f"    Reason: {check.block_reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous agent with SCP enforcement")
    parser.add_argument("--hostname", default="worker-node-07", help="Target hostname")
    args = parser.parse_args()

    run_autonomous_agent(args.hostname)
    sys.exit(0)


if __name__ == "__main__":
    main()
