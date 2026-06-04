# SCP Specification v1.0 -- Skill Contracts Protocol

## Overview

SCP (Skill Contracts Protocol) defines a declarative contract for LLM agent skills. A skill contract specifies:

- **What tools** the agent is allowed to use
- **What steps** it should follow (query plan)
- **What evidence** it must collect before finishing
- **When it can finalize** (evidence gates and iteration minimums)
- **Tool overrides** for aliasing legacy tool names

The contract lives as YAML frontmatter in a SKILL.md file (or as standalone YAML/JSON), making it portable across agent frameworks. SCP extends the [agentskills.io](https://agentskills.io) format with enforceable runtime constraints.

## Frontmatter Format

A SKILL.md file with SCP constraints uses standard YAML frontmatter delimited by `---`:

```yaml
---
scp: "1.0"
name: <string>            # required
description: <string>     # required
activation:               # optional, exclusive invocation routes
  triggers: [...]
  slash_command: <string>
constraints:              # optional, the SCP contract
  tool_ids: [...]
  plan: [...]
  evidence: { required: [...] }
  finalization: { ... }
  tool_overrides: { ... }
---

# Markdown body

Free-form skill documentation follows the frontmatter.
```

The `scp` key signals that this file contains an SCP contract. Its value is the spec version (`"1.0"`).

Files without a `constraints` block are valid SCP files -- they simply have no enforcement rules.

## Fields

### Top-Level

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `scp` | string | yes | Spec version. Must be `"1.0"` for this version. |
| `name` | string | yes | Unique skill identifier (kebab-case recommended). |
| `description` | string | yes | One-line human-readable summary. |
| `activation` | object | no | Exclusive invocation routes. When absent the skill is always discoverable. When present the skill is invocable **only** through its declared routes. See below. |
| `constraints` | object | no | The enforcement contract. See below. |
| `delegates_to` | list of strings | no | Child skill names this skill may delegate to. During delegation the child's `tool_ids` are merged into the parent's allowed set. |

### `activation`

When the `activation` block is **absent**, the skill is always discoverable -- any orchestrator may select it freely.

When `activation` is **present**, the skill uses an **exclusive** activation model: it is invocable only through the routes declared in the block (triggers, slash command, attachment types). The `auto_discover` flag controls whether the orchestrator may *also* select it outside those explicit routes.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `triggers` | list of strings | no | Keywords for automatic selection. |
| `slash_command` | string | no | Explicit invocation name (e.g. `/investigate`). |
| `attachment_types` | list of strings | no | Data-driven activation by attachment type (e.g. `alert`, `case`). |
| `auto_discover` | boolean | no | Whether the orchestrator may *also* select this skill outside the explicit routes. Default: `true`. |

### `constraints`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enforcement` | string | no | How strictly the contract is enforced: `strict` (reject violations), `soft` (warn + approve), `off` (pass-through). Default: `strict`. |
| `tool_ids` | list of strings | no | Tool names the agent may call. If present, calls to unlisted tools are rejected. If absent, all tools are allowed. |
| `plan` | list of PlanStep | no | Ordered steps the agent should execute before free-form investigation. |
| `evidence` | object | no | Evidence requirements for finalization. |
| `finalization` | object | no | Rules governing when the agent may produce its final output. |
| `tool_overrides` | map (string -> string) | no | Alias mapping: keys are legacy/generic names, values are actual tool names. |
| `referenced_content` | list of ReferencedContent | no | Named supplementary content blocks the agent can read selectively. |

### PlanStep

Each entry in `constraints.plan`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tool` | string | yes | Tool name to invoke. Must appear in `tool_ids` if that list is defined. |
| `description` | string | yes | Human-readable explanation of what this step does. |
| `args_template` | object | no | Pre-filled arguments. May contain `{{variable}}` placeholders for runtime interpolation. |
| `delegates` | string | no | Child skill name to delegate to at this step. Activates the child contract's `tool_ids` for the duration of the delegation. Must be listed in the top-level `delegates_to`. |
| `requires_evidence` | list of strings | no | Evidence IDs that must be collected before this step's tool is allowed. Blocks the tool call until all listed evidence items are recorded. |

### `constraints.evidence`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `required` | list of EvidenceItem | yes | Evidence the agent must collect before finalization. |
| `detection` | list of EvidenceDetectionRule | no | Regex-based rules for automatic evidence detection from tool outputs. |

### EvidenceItem

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Machine-readable identifier (snake_case). |
| `description` | string | yes | Human-readable explanation of what constitutes this evidence. |

### EvidenceDetectionRule

Each entry in `constraints.evidence.detection`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `evidence_id` | string | yes | ID matching a required evidence item in `evidence.required`. |
| `tool_pattern` | regex string | yes | Python regex matched against the tool name (e.g. `^slack_get_thread$`). |
| `result_pattern` | regex string | no | Python regex searched against the stringified tool result. If omitted, a tool name match alone satisfies the evidence. |

Detection rules enable **deterministic** evidence tracking without relying on LLM reasoning. When a tool call matches `tool_pattern` and (optionally) the result matches `result_pattern`, the corresponding evidence item is automatically marked as collected.

### ReferencedContent

Each entry in `constraints.referenced_content`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique name for this content block. |
| `path` | string | no | Relative path hint (e.g. `./queries`). Used by adapters to generate references. |
| `content` | string | no | Inline Markdown content. |
| `required` | boolean | no | If `true`, the agent must consult this block before finalizing. Default: `false`. |

### `constraints.finalization`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `require_all_evidence` | boolean | no | If `true`, all required evidence must be collected before finalization. Default: `true`. |
| `min_iterations` | integer | no | Minimum number of tool-call iterations before finalization is allowed. Default: `0`. |

## Validation Rules

A valid SCP contract must satisfy:

1. **Schema conformance**: All fields match the types specified above and in `scp-schema.json`.
2. **Plan-tools consistency**: Every `tool` in `plan` steps must appear in `tool_ids` (when `tool_ids` is defined).
3. **Tool-overrides consistency**: Every value in `tool_overrides` must appear in `tool_ids` (when `tool_ids` is defined).
4. **Evidence ID uniqueness**: No duplicate `id` values within `evidence.required`.
5. **Non-negative iterations**: `finalization.min_iterations` must be >= 0.

## Template Interpolation

`args_template` values may contain `{{variable}}` placeholders:

```yaml
args_template:
  query: "FROM index-* | WHERE domain == '{{service_domain}}'"
  timeout_seconds: 30
```

Placeholders are resolved at runtime by the agent framework. Unresolved placeholders should be treated as errors.

## Backward Compatibility

Files without the `scp` key are not SCP files. Parsers should ignore them gracefully.

Files with `scp: "1.0"` but no `constraints` block are valid -- they declare participation in the protocol but impose no enforcement.

## Delegation

A skill may delegate to child skills using the `delegates_to` field. This enables a parent skill to temporarily expand its allowed tool set when invoking a child skill's workflow.

### Semantics

1. The parent contract declares `delegates_to: [child-skill-name, ...]`.
2. Plan steps may reference a child via `delegates: child-skill-name`.
3. When a delegation is active, the enforcer merges the child's `tool_ids` into the parent's allowed set.
4. Multiple levels of delegation are supported (stack-based).
5. The child contract must be loadable at runtime (file path resolved via skill directories).

### Example

```yaml
scp: "1.0"
name: slack-alert-reader
delegates_to:
  - ecp-traffic-alert-investigation
constraints:
  tool_ids:
    - slack_get_thread
    - slack_post_message
    - slack_add_reaction
  plan:
    - tool: slack_get_thread
      description: Read the alert thread
    - tool: delegate
      description: Investigate the alert
      delegates: ecp-traffic-alert-investigation
    - tool: slack_post_message
      description: Post investigation results
```

### Contract Stacking

When the enforcer pushes a delegation:
- The child's `tool_ids` are unioned with the parent's
- If the child has `tool_ids: null` (unconstrained), the merged set becomes unconstrained
- Pop returns to the parent's original constraint set

## Enforcement Modes

The `constraints.enforcement` field controls how violations are handled at runtime:

| Mode | Behaviour |
|------|-----------|
| `strict` | Reject the tool call with an error reason. The agent must comply. (Default) |
| `soft` | Log a warning but approve the tool call. Useful for development/debugging. |
| `off` | Pass-through — no enforcement. Useful for disabling SCP without removing the contract. |

### Environment Variable Override

The `SCP_MODE` environment variable overrides the contract's declared mode:

```bash
SCP_MODE=soft   # Downgrade all skills to soft mode
SCP_MODE=off    # Disable enforcement entirely
SCP_MODE=strict # Force strict even if contract says soft
```

This allows operators to tune enforcement without modifying skill files.

## Plan Step Enforcement

When a `constraints.plan` is present, the enforcer tracks step ordering:

1. **Step order**: A tool matching step N+1 is blocked until step N's tool has been called.
2. **Retries**: A tool matching a past (completed) step is always allowed.
3. **Utility tools**: Tools not listed in any plan step pass through freely.
4. **Auto-delegation**: When a step declares `delegates`, the child skill's tool_ids are pushed onto the enforcement stack upon reaching that step and popped when the next parent step fires.

### Evidence-Gated Steps

When a plan step declares `requires_evidence`, the step's tool is blocked until all listed evidence IDs have been collected (via post-tool detection rules):

```yaml
plan:
  - tool: read_slack
    description: Read the thread
  - tool: post_reply
    description: Post the summary
    requires_evidence:
      - thread_content
      - alert_classification
```

This ensures the agent cannot produce output until prerequisite information has been gathered.

## Limitations

### L1: Reasoning-Step Evidence

Evidence items that require LLM reasoning (e.g., "correctly identified root cause", "proposed appropriate remediation") cannot be verified deterministically by external enforcement. These must remain as prose-based instructions in the skill's markdown body.

Detection rules only work for evidence that is observable from tool I/O: tool names and their stringified results.

### L2: Skill Activation Detection

In hook-based enforcement (e.g., Cursor hooks), the system has limited visibility into which skill is currently active. Activation is inferred from:

1. Slash commands in the initial user message (highest confidence)
2. Keyword triggers matched against the user message
3. Environment-provided skill path overrides

If no activation signal is detected, hooks operate in **pass-through mode** (all tools allowed). This means enforcement is opt-in and requires clear invocation patterns.

## Schema

The machine-readable JSON Schema is at `scp-schema.json` in this directory.

## Examples

See the `examples/` directory for annotated skill files demonstrating various constraint configurations.
