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
triggers: [<string>, ...] # optional, keywords for skill selection
constraints:              # optional, the OpenSkills contract
  allowed_tools: [...]
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
| `triggers` | list of strings | no | Keywords that help an orchestrator select this skill. |
| `constraints` | object | no | The enforcement contract. See below. |

### `constraints`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `allowed_tools` | list of strings | no | Tool names the agent may call. If present, calls to unlisted tools are rejected. If absent, all tools are allowed. |
| `plan` | list of PlanStep | no | Ordered steps the agent should execute before free-form investigation. |
| `evidence` | object | no | Evidence requirements for finalization. |
| `finalization` | object | no | Rules governing when the agent may produce its final output. |
| `tool_overrides` | map (string -> string) | no | Alias mapping: keys are legacy/generic names, values are actual tool names. |

### PlanStep

Each entry in `constraints.plan`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tool` | string | yes | Tool name to invoke. Must appear in `allowed_tools` if that list is defined. |
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

### `constraints.finalization`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `require_all_evidence` | boolean | no | If `true`, all required evidence must be collected before finalization. Default: `true`. |
| `min_iterations` | integer | no | Minimum number of tool-call iterations before finalization is allowed. Default: `0`. |

## Validation Rules

A valid OpenSkills contract must satisfy:

1. **Schema conformance**: All fields match the types specified above and in `openskills-schema.json`.
2. **Plan-tools consistency**: Every `tool` in `plan` steps must appear in `allowed_tools` (when `allowed_tools` is defined).
3. **Tool-overrides consistency**: Every value in `tool_overrides` must appear in `allowed_tools` (when `allowed_tools` is defined).
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
