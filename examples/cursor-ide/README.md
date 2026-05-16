# OpenSkills + Cursor IDE

This example shows how to enhance a Cursor skill with OpenSkills
constraints so the agent follows a structured plan instead of
freestyling.

## Before: Standard SKILL.md

A typical Cursor skill is free-form markdown with minimal frontmatter:

```yaml
---
name: investigate-latency
description: Investigate service latency spikes.
tools: [Bash, Read]
triggers: [latency, slo burn]
---

# Investigate Latency

1. Check if data exists
2. Compute percentiles
3. Analyze error rates
4. Write report
```

The agent reads this as *guidance* but has no guardrails. It might skip
steps, call tools you didn't intend, or finalize before collecting
enough evidence.

## After: OpenSkills-Enhanced SKILL.md

Add an `openskills` version and a `constraints` block to the same file:

```yaml
---
openskills: "1.0"
name: investigate-latency
description: Investigate service latency spikes.
tools: [Bash, Read]
triggers: [latency, slo burn]
constraints:
  allowed_tools:
    - run_es_query
    - generate_report
  plan:
    - tool: run_es_query
      description: Fetch raw data for the target service
    - tool: run_es_query
      description: Compute latency percentiles
    - tool: run_es_query
      description: Check error rate distribution
  evidence:
    required:
      - id: data_presence
        description: Data exists for the target service and time window.
      - id: latency_stats
        description: Percentile-based latency distribution is computed.
      - id: error_correlation
        description: Errors are correlated with latency spikes.
  finalization:
    require_all_evidence: true
    min_iterations: 1
---

# Investigate Latency
...
```

The markdown body stays the same. The `constraints` block is what
OpenSkills adds.

## How to Use

1. Copy `investigate-latency/SKILL.md` into your project's
   `.cursor/skills/investigate-latency/` directory.

2. When you ask Cursor to investigate a latency issue, the agent will
   now have structured directives injected into its context:
   - Only `run_es_query` and `generate_report` are allowed
   - Three plan steps to execute in order
   - Three evidence items to collect before finalizing
   - Cannot finalize until all evidence is present and at least one
     iteration of tool calls is complete

3. The `constraints` block is backward-compatible -- agents that don't
   understand OpenSkills simply ignore it and use the markdown body.

## Validating Your Skill

```bash
pip install openskills
openskills validate .cursor/skills/investigate-latency/SKILL.md
```

## What Changes for the Agent?

| Aspect | Standard SKILL.md | OpenSkills SKILL.md |
|--------|-------------------|---------------------|
| Tool usage | Any tool available | Only `allowed_tools` |
| Investigation order | Agent decides | `plan` steps first, then free-form |
| Completeness | Agent decides when done | Must collect all `evidence.required` |
| Early termination | Can stop anytime | Blocked until `finalization` rules met |
| Backward compat | N/A | Non-OpenSkills agents ignore `constraints` |
