---
openskills: "1.0"
name: investigate-log-errors
description: Triage application log errors by severity, affected service, and host. Use when a user asks to investigate or summarize log errors.
triggers: [log errors, error triage, application failures]
constraints:
  allowed_tools:
    - platform.core.execute_esql
    - platform.core.generate_esql
    - platform.core.list_indices
  plan:
    - tool: platform.core.execute_esql
      description: Query recent error logs grouped by service
      args_template:
        query: "FROM logs-* | WHERE log.level == 'error' AND @timestamp >= '{{start_time}}' | STATS error_count=COUNT(*) BY service.name | SORT error_count DESC | LIMIT 20"
    - tool: platform.core.execute_esql
      description: Get error details for the top affected service
      args_template:
        query: "FROM logs-* | WHERE log.level == 'error' AND service.name == '{{service_name}}' | SORT @timestamp DESC | LIMIT 50"
  evidence:
    required:
      - id: error_distribution
        description: Error counts are broken down by service.
      - id: error_details
        description: Representative error messages from the top service are retrieved.
      - id: severity_assessment
        description: Severity is assessed based on error rate and impact.
  finalization:
    require_all_evidence: true
    min_iterations: 1
---

# Log Error Triage

## When to Use This Skill

Use this skill when:
- A user asks to investigate or summarize log errors
- A user wants to understand the cause of application failures
- An alert fires for elevated error rates

## Triage Process

### 1. Identify affected services
Query recent error logs and group by `service.name` to find the most impacted services.

### 2. Classify by severity
- **Critical**: Error rate > 5% or affecting core services
- **High**: Error rate 1-5% or affecting multiple services
- **Medium**: Isolated errors in non-critical services
- **Low**: Sporadic errors with no pattern

### 3. Investigate top service
Retrieve representative error messages and stack traces from the most affected service.

### 4. Suggest remediation
Based on error patterns, suggest next steps (restart, rollback, config change, etc.).

## Edge Cases

- **No errors found**: Confirm the time window and indices are correct.
- **Too many services affected**: Group by error type first, then by service.
- **Missing log.level field**: Fall back to message-based pattern matching.
