# Autonomous Agent with SCP Enforcement

This example demonstrates the core use case for SCP: an agent that runs
**without human supervision** and needs a machine-readable definition of
done.

## The Problem

Autonomous agents -- remote MCP servers, background workers, webhook
handlers -- run in a loop making decisions. Without explicit contracts:

1. **Premature finalization**: The agent calls one tool, gets a partial
   answer, and declares itself done. The human receives a shallow report
   and has to redo the investigation.

2. **Tool drift**: The agent calls `delete_node` when you only wanted
   `get_node_metrics`. In an autonomous context there's no human to
   catch this before execution.

3. **Step skipping**: The agent cherry-picks the easy queries and skips
   the hard correlation step. The report looks complete but misses the
   root cause.

## The Solution

Pass an SCP contract to the agent. The contract defines:

- **`tool_ids`**: Only these tools may be called (everything else is blocked)
- **`plan`**: Execute these steps in order before free-form investigation
- **`evidence.required`**: These facts must be collected before the agent can finish
- **`finalization`**: Cannot stop until all evidence is present AND at least N iterations complete

The agent's loop becomes:

```
load contract
while not enforcer.can_finalize(tracker):
    decide next action (plan step or LLM-chosen)
    gate the tool call (enforcer.check_tool_call)
    execute the tool
    record evidence from the result
    increment iteration
produce final report
```

## Files

| File | Purpose |
|------|---------|
| `skill.yaml` | SCP contract for host health investigation |
| `agent_loop.py` | Working agent loop with enforcement (mock tools) |

## Running

```bash
# From the repo root
uv run python examples/autonomous-agent/agent_loop.py

# With a custom hostname
uv run python examples/autonomous-agent/agent_loop.py --hostname my-node-01
```

## Where This Pattern Applies

| Use Case | Transport | SCP Role |
|----------|-----------|----------|
| Remote MCP server | MCP protocol | Contract passed as skill metadata |
| PagerDuty webhook handler | HTTP | Contract loaded at alert ingestion |
| LangGraph background node | In-process | Contract wraps the node's tool calls |
| Cron-based audit agent | CLI | Contract defines audit completeness |
| Slack bot investigation | WebSocket | Contract ensures thorough response |

The contract is transport-agnostic. SCP doesn't care *how* the agent
runs -- it cares *what the agent must prove* before it can stop.

## Key Difference from `python-app/`

The `python-app/` example shows how to use SCP in a synchronous,
human-attended loop. This example emphasizes the **autonomous** pattern
where:

- No human is watching each step
- The agent must keep going until the contract is satisfied
- Tool gating prevents destructive actions (delete, drain, reboot)
- Evidence gates prevent shallow reports
- The output goes directly to an incident channel or API
