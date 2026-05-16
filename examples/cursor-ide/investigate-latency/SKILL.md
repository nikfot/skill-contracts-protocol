---
openskills: "1.0"
name: investigate-latency
description: Investigate service latency spikes using structured evidence collection.
tools: [Bash, Read]
triggers: [latency, slo burn, p99, high response time]
constraints:
  allowed_tools:
    - run_es_query
    - read_knowledge
    - generate_report
  plan:
    - tool: run_es_query
      description: Fetch raw probe data for the target service and time window
      args_template:
        query_type: esql
        query: "FROM heartbeat-* | WHERE url.domain == '{{service_domain}}' AND @timestamp >= '{{start_time}}' | LIMIT 200"
    - tool: run_es_query
      description: Compute latency percentiles (p50, p95, p99) over the alert window
      args_template:
        query_type: esql
        query: "FROM heartbeat-* | WHERE url.domain == '{{service_domain}}' | STATS p50=PERCENTILE(http.rtt.total.us, 50), p95=PERCENTILE(http.rtt.total.us, 95), p99=PERCENTILE(http.rtt.total.us, 99)"
    - tool: run_es_query
      description: Analyze HTTP status code distribution to correlate errors with latency
      args_template:
        query_type: esql
        query: "FROM heartbeat-* | WHERE url.domain == '{{service_domain}}' | STATS total=COUNT(*) BY http.response.status_code | SORT total DESC | LIMIT 20"
  evidence:
    required:
      - id: data_presence
        description: Probe data exists for the target service and time window.
      - id: latency_stats
        description: Percentile-based latency distribution (p50/p95/p99) is computed.
      - id: error_correlation
        description: HTTP status codes are analyzed to correlate errors with latency.
  finalization:
    require_all_evidence: true
    min_iterations: 1
  tool_overrides:
    investigation_setup: run_es_query
---

# Investigate Service Latency

## When to Use

- Alert indicates elevated latency (SLO burn rate, p99 spike, high response time)
- Alert is service/domain-based (e.g. `sla.<region>.aws.found.io`)
- You need to determine whether latency is service-side or network-path related

## Inputs

- `service_domain`: The target service domain from the alert
- `start_time`: ISO-8601 timestamp for the alert window start
- Optional: `region` for scoping the investigation

## Investigation Flow

1. **Verify data exists** for the target service in the observation window
2. **Compute latency percentiles** (p50, p95, p99) to quantify the problem
3. **Analyze error rates** by HTTP status code to find correlated failures
4. **Synthesize findings** into an actionable report

## Expected Output

A structured report containing:
- Latency distribution with percentile breakdowns
- Error rate analysis and status code distribution
- Assessment of whether latency is service-internal or path-related
- Recommended next steps
