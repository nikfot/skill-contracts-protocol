# OpenSkills

Declarative skill contracts for LLM agents -- define what tools to use, what evidence to collect, and when to finalize.

## What is this?

LLM agents today either freestyle (no guardrails) or have orchestration logic baked into framework code. OpenSkills puts that logic into a portable, declarative contract: what tools the agent can use, what steps it should follow, what evidence it must collect before it can finish. One spec, any framework -- drop it into Cursor skills, LangGraph, PydanticAI, or your own agent loop.

## Quick Example

Add an `openskills` constraints block to any SKILL.md frontmatter:

```yaml
---
openskills: "1.0"
name: investigate-latency
description: Investigate service latency spikes
activation:
  triggers: [latency, slo burn, p99]
constraints:
  tool_ids:
    - run_es_query
    - generate_report
  plan:
    - tool: run_es_query
      description: Fetch raw latency data
      args_template:
        query: "FROM heartbeat-* | WHERE url.domain == '{{domain}}'"
    - tool: run_es_query
      description: Compute percentiles
  evidence:
    required:
      - id: data_presence
        description: Data exists for target service
      - id: latency_distribution
        description: Percentile stats are computed
  finalization:
    require_all_evidence: true
    min_iterations: 1
---

# Investigate Latency

Your regular skill markdown content here...
```

## Install

```bash
uv add openskills
# or
pip install openskills
```

## Validate skill files

```bash
openskills validate path/to/skills/
```

## Use the runtime

```python
from openskills import load_skill
from openskills.runtime import SkillEnforcer, EvidenceTracker, PlanExecutor

contract = load_skill("path/to/SKILL.md")
enforcer = SkillEnforcer(contract)
tracker = EvidenceTracker(contract)
planner = PlanExecutor(contract)

# In your agent loop:
for step in planner:
    result = your_tool_runner(step.tool, step.args)
    tracker.record(result)
    if enforcer.should_finalize(tracker):
        break
```

## Package Contents

| Module | Purpose |
|--------|---------|
| `openskills.models` | Pydantic models: `SkillContract`, `Evidence`, `QueryStep`, `FinalizationRules` |
| `openskills.loader` | Parse SKILL.md YAML frontmatter into `SkillContract` |
| `openskills.validator` | Referential integrity checks (tool_ids vs plan steps) |
| `openskills.cli` | CLI: `openskills validate <file\|dir>` |
| `openskills.runtime` | Enforcement engine: `SkillEnforcer`, `EvidenceTracker`, `PlanExecutor` |
| `openskills.adapters` | System-prompt builder from `SkillContract` |

## How is this different from Cursor skills?

Cursor skills tell the agent *what to do*; OpenSkills tells it *how to stay on track* -- tool guardrails, evidence gates, and finalization rules that no SKILL.md can express today.

## License

MIT
