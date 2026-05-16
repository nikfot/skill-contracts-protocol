# The Problem OpenSkills Solves

## TL;DR

Today's LLM agent skills describe *what to do* but cannot *enforce how
it gets done*. Agents skip steps, call unintended tools, and finalize
with incomplete evidence. OpenSkills turns guidance into a contract.

## A Concrete Example

You have a latency investigation skill. You give it to an agent:

```yaml
---
name: investigate-latency
description: Investigate service latency spikes.
tools: [Bash, Read]
triggers: [latency, slo burn]
---

# Investigate Latency

1. Check if data exists for the service
2. Compute latency percentiles (p50, p95, p99)
3. Correlate with HTTP error rates
4. Generate report
```

You ask: *"Investigate the latency spike on sla.eu-west-1.aws.found.io
at 14:00 UTC."*

### What happens without OpenSkills

The agent reads the markdown, treats the numbered list as *suggestions*,
and does this:

1. Calls `run_es_query` -- finds data exists. Good.
2. Calls `run_es_query` -- computes p95/p99 numbers. Good.
3. **Decides it has enough** and writes a report.

The report says:

> *Latency p99 is elevated at 1200ms. Recommend investigating further.*

What went wrong:

- **Skipped step 3** entirely -- error rate correlation was never done.
- **Finalized with incomplete evidence** -- no one knows if the latency
  is caused by 5xx errors, network path issues, or a backend regression.
- The phrase "recommend investigating further" is the agent admitting it
  didn't finish, but nothing stopped it from declaring itself done.

In a real incident, an SRE reads this report, sees the gap, and redoes
the investigation manually. The skill *described* the right process but
couldn't *enforce* it.

### What happens with OpenSkills

Same skill, same markdown body, but with a `constraints` block added:

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
  evidence:
    required:
      - id: data_presence
        description: Data exists for the service.
      - id: latency_stats
        description: p50/p95/p99 are computed.
      - id: error_correlation
        description: Errors are correlated with latency.
  finalization:
    require_all_evidence: true
    min_iterations: 1
---

# Investigate Latency
(same markdown body)
```

Now the enforcement layer kicks in:

1. Agent calls `run_es_query` -- data exists. Evidence: `data_presence`
   collected.
2. Agent calls `run_es_query` -- percentiles computed. Evidence:
   `latency_stats` collected.
3. Agent tries to finalize. **Blocked.** `error_correlation` is still
   missing.
4. Agent is forced to run the error rate query. Evidence:
   `error_correlation` collected.
5. All evidence present, min_iterations met. Finalization allowed.
6. Report includes all three analyses -- complete and actionable.

## The Difference

| Aspect | Without OpenSkills | With OpenSkills |
|--------|-------------------|-----------------|
| Steps completed | 2 of 3 | 3 of 3 |
| Evidence gaps | error_correlation missing | None |
| Report quality | Partial, hedging | Complete, actionable |
| Human redo needed | Yes | No |
| Time wasted | Agent time + human redo | Agent time only |

## Three Failure Modes OpenSkills Prevents

### 1. Premature Finalization

The agent thinks it's done before it is. It saw some data, generated
some text, and stopped. Without evidence gates, there is no mechanism
to say "you haven't proven X yet."

**OpenSkills fix:** `evidence.required` defines what must be collected.
`finalization.require_all_evidence: true` blocks early termination.

### 2. Tool Drift

The agent calls tools you didn't intend. Maybe it tries to
`delete_pod` instead of `get_pod`, or calls a tool that modifies state
during a read-only investigation.

**OpenSkills fix:** `allowed_tools` is a whitelist. Calls to unlisted
tools are blocked before execution.

### 3. Step Skipping

The agent cherry-picks the easy steps (fetch data, compute a stat) and
skips the hard ones (cross-correlate, decompose by dimension). The
markdown says "do these 4 things" but the agent does 2.

**OpenSkills fix:** `plan` defines ordered steps that execute
deterministically before the agent gets free-form control. Combined
with evidence gates, skipping a step means missing evidence, which
blocks finalization.

## Why Not Just Write a Better Prompt?

You can. And it helps -- for a while. But:

- **Prompts drift.** Every LLM update changes how instructions are
  followed. A constraint that worked with GPT-4 may be ignored by
  GPT-5.
- **Prompts don't compose.** If you have 50 skills, you need 50
  carefully crafted prompts. OpenSkills constraints are structured data
  that tools can validate, not prose that models interpret.
- **Prompts can't be verified.** You can't run `openskills validate`
  on a system prompt to check that all plan steps reference allowed
  tools. You can with a contract.
- **Prompts are invisible.** When the agent misbehaves, you read logs
  and guess what went wrong. With OpenSkills, the enforcer tells you
  exactly which evidence was missing or which tool was blocked.

## The One-Liner

Without OpenSkills, a SKILL.md is a *hope*. With it, it's a *contract*.
