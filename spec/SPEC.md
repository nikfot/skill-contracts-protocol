# OpenSkills Specification v1.0

## Overview

OpenSkills defines a declarative contract for LLM agent skills. A skill contract specifies:

- **What tools** the agent is allowed to use
- **What steps** it should follow (query plan)
- **What evidence** it must collect before finishing
- **When it can finalize** (evidence gates and iteration minimums)
- **Tool overrides** for aliasing legacy tool names

The contract lives as YAML frontmatter in a SKILL.md file (or as standalone YAML/JSON), making it portable across agent frameworks.

## Frontmatter Format

A SKILL.md file with OpenSkills constraints uses standard YAML frontmatter delimited by `---`:

```yaml
---
openskills: "1.0"
name: <string>            # required
description: <string>     # required
activation:               # optional, exclusive invocation routes
  triggers: [...]
  slash_command: <string>
constraints:              # optional, the OpenSkills contract
  tool_ids: [...]
  plan: [...]
  evidence: { required: [...] }
  finalization: { ... }
  tool_overrides: { ... }
---

# Markdown body

Free-form skill documentation follows the frontmatter.
```

The `openskills` key signals that this file contains an OpenSkills contract. Its value is the spec version (`"1.0"`).

Files without a `constraints` block are valid OpenSkills files -- they simply have no enforcement rules.

## Fields

### Top-Level

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `openskills` | string | yes | Spec version. Must be `"1.0"` for this version. |
| `name` | string | yes | Unique skill identifier (kebab-case recommended). |
| `description` | string | yes | One-line human-readable summary. |
| `activation` | object | no | Exclusive invocation routes. When absent the skill is always discoverable. When present the skill is invocable **only** through its declared routes. See below. |
| `constraints` | object | no | The enforcement contract. See below. |

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

### `constraints.evidence`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `required` | list of EvidenceItem | yes | Evidence the agent must collect before finalization. |

### EvidenceItem

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Machine-readable identifier (snake_case). |
| `description` | string | yes | Human-readable explanation of what constitutes this evidence. |

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

A valid OpenSkills contract must satisfy:

1. **Schema conformance**: All fields match the types specified above and in `openskills-schema.json`.
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

Files without the `openskills` key are not OpenSkills files. Parsers should ignore them gracefully.

Files with `openskills: "1.0"` but no `constraints` block are valid -- they declare participation in the spec but impose no enforcement.

## Schema

The machine-readable JSON Schema is at `openskills-schema.json` in this directory.

## Examples

See the `examples/` directory for annotated skill files demonstrating various constraint configurations.
