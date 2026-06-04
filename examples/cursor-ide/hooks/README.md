# SCP Cursor IDE Hooks

Enforce SCP skill contracts in [Cursor IDE](https://cursor.com) using the hooks system.

## How It Works

Cursor hooks allow you to run scripts before/after agent events. SCP uses three hooks:

| Hook | Event | Purpose | failClosed |
|------|-------|---------|------------|
| `scp-session.py` | `sessionStart` | Detect active skill from user message | No |
| `scp-enforcer.py` | `preToolUse` | Gate tool calls against contract | **Yes** |
| `scp-evidence.py` | `postToolUse` | Detect evidence from tool results via regex | No |

### Enforcement Flow

```
User message → sessionStart hook → detect skill contract
                                 → persist SessionState to /tmp/scp-session-{pid}.json

Tool call → preToolUse hook → load state → resolve enforcement mode
                            → check tool against tool_ids (+ delegation merges)
                            → check plan step ordering
                            → check evidence gates (requires_evidence)
                            → advance step index on match
                            → APPROVE or REJECT (or WARN in soft mode)

Tool result → postToolUse hook → load state → check detection rules
                               → record satisfied evidence → persist state
```

### Key Design Decisions

- **`failClosed: true`** on `preToolUse` means if the hook script crashes, the tool call is blocked. This ensures the contract is always enforced.
- **`failClosed: false`** on evidence detection and session start means failures degrade gracefully without blocking the agent.

## Installation

### Quick Start (recommended)

1. Clone or download the SCP repo:

```bash
git clone https://github.com/nikfot/skill-contracts-protocol.git ~/.local/share/scp
```

2. Put `scp-hook` on your PATH:

```bash
ln -sf ~/.local/share/scp/examples/cursor-ide/hooks/scp-hook ~/.local/bin/scp-hook
```

3. Copy `hooks.json` to any project you want SCP enforcement in:

```bash
cp ~/.local/share/scp/examples/cursor-ide/hooks/hooks.json /path/to/project/.cursor/hooks.json
```

That's it. The `scp-hook` script auto-detects:
- **SCP library location** from `SCP_HOME` env var, or searches `~/.local/share/scp`, `~/github/nikfot/skill-contracts-protocol`, `~/src/skill-contracts-protocol`, `~/.scp`
- **Skills directory** from `SCP_SKILL_DIRS` env var, or defaults to `~/.cursor/skills`
- **Python runtime** using `uv run` (preferred), project `.venv`, or system Python with PYTHONPATH

### Environment Variables (all optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `SCP_HOME` | Auto-detected | Path to the `skill-contracts-protocol` checkout |
| `SCP_SKILL_DIRS` | `~/.cursor/skills` | Colon-separated dirs to scan for SKILL.md files |
| `SCP_PYTHON` | Auto-detected | Python interpreter with `scp` installed |
| `SCP_MODE` | Contract's `enforcement` field | Override enforcement mode: `strict`, `soft`, or `off` |

### Alternative: pip install

If you prefer not to use `uv run`, install the library globally:

```bash
pip install --user -e ~/.local/share/scp
# Then set SCP_PYTHON to your system python:
export SCP_PYTHON=python3
```

### The hooks.json file

The portable `hooks.json` uses a single dispatcher script:

```json
{
  "hooks": [
    { "event": "sessionStart", "script": "scp-hook sessionStart", "failClosed": false },
    { "event": "preToolUse",   "script": "scp-hook preToolUse",   "failClosed": true },
    { "event": "postToolUse",  "script": "scp-hook postToolUse",  "failClosed": false }
  ]
}
```

If `scp-hook` isn't on PATH, the hook fails open (approves everything) so it never blocks a session where SCP isn't installed.

## Enforcement Modes

Control how violations are handled via the `constraints.enforcement` field or `SCP_MODE` env var:

| Mode | Behaviour |
|------|-----------|
| `strict` | Reject the tool call. The agent must comply. (Default) |
| `soft` | Log a warning but approve. Useful for development or observing model deviations. |
| `off` | Pass-through. No enforcement. |

Environment variable takes precedence over the contract field:

```bash
# Temporarily disable for debugging
SCP_MODE=off cursor .

# Run in soft mode to observe what would be blocked
SCP_MODE=soft cursor .
```

## Plan Step Enforcement

When a contract defines `constraints.plan`, the hook enforces execution order:

```yaml
constraints:
  tool_ids:
    - slack_get_thread
    - esql_query
    - post_reply
  plan:
    - tool: slack_get_thread
      description: Read the alert thread
    - tool: esql_query
      description: Query Elasticsearch for context
    - tool: post_reply
      description: Post the investigation summary
      requires_evidence:
        - thread_content
        - es_data
```

### Step Rules

1. **Sequential**: Step N+1's tool is blocked until step N's tool fires.
2. **Retries allowed**: Calling a past step's tool again is always OK.
3. **Utility passthrough**: Tools not in any step (e.g., `Read`, `Grep`) are never blocked by step ordering.
4. **Evidence gates**: Steps with `requires_evidence` are blocked until all listed evidence IDs are collected.

### Automatic Step Advancement

When a tool call matches the current step's tool:
1. The step is marked completed
2. `current_step_index` advances
3. If the step has `delegates`, the child skill is pushed onto the delegation stack
4. State is persisted

## Evidence Detection

Evidence can be automatically detected from tool outputs using regex rules:

```yaml
constraints:
  evidence:
    required:
      - id: thread_content
        description: "Slack thread content retrieved"
      - id: alert_classified
        description: "Alert classified by ownership"
    detection:
      - evidence_id: thread_content
        tool_pattern: "^slack_get_thread$"
        result_pattern: "messages.*text"
      - evidence_id: alert_classified
        tool_pattern: "^slack_get_thread$"
        result_pattern: "(ecp-traffic|proxy|ingress)"
```

### Detection Rule Fields

| Field | Type | Description |
|-------|------|-------------|
| `evidence_id` | string | ID matching a required evidence item |
| `tool_pattern` | regex | Pattern matched against the tool name |
| `result_pattern` | regex (optional) | Pattern searched in the stringified tool result |

If `result_pattern` is omitted, a tool name match alone satisfies the evidence.

## Delegation

Skills can delegate to child skills using `delegates_to` and `plan[].delegates`:

```yaml
scp: "1.0"
name: slack-alert-reader
delegates_to:
  - ecp-traffic-alert-investigation
constraints:
  tool_ids:
    - slack_get_thread
    - slack_post_message
  plan:
    - tool: slack_get_thread
      description: Read the alert thread
    - tool: investigate
      description: Delegate to investigation skill
      delegates: ecp-traffic-alert-investigation
    - tool: slack_post_message
      description: Post the summary
      requires_evidence:
        - investigation_result
```

During delegation, the child contract's `tool_ids` are merged with the parent's allowed set. When the next parent step fires, the delegation is automatically popped.

## State File

Session state is stored at `/tmp/scp-session-{pid}.json`:

```json
{
  "active_skill_path": "/home/user/.cursor/skills/slack-alert-reader/SKILL.md",
  "collected_evidence": ["thread_content"],
  "delegation_stack": [],
  "current_step_index": 1,
  "completed_steps": [0],
  "iteration": 2
}
```

The file is created on session start and updated after each tool call.

## Limitations

### L1: Reasoning-step evidence

Evidence that requires LLM reasoning (e.g., "correctly identified root cause") cannot be verified deterministically by hooks. These must remain prose-based instructions in the skill's markdown body.

### L2: Skill activation detection

Cursor hooks receive limited context about which skill is active. The `sessionStart` hook infers activation from:
1. Slash commands in the initial message (e.g., `/slack-alert-reader`)
2. Keyword triggers defined in the contract's `activation.triggers`

If the agent is invoked without a clear trigger, the hooks operate in pass-through mode (all tools allowed).

### L3: Final output gating

The hook system can only gate tool calls. If the final action is a text message (not a tool call), it cannot be blocked. Use a `post_reply` or `submit_response` tool as the final plan step to make output gatable.
