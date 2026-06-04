# SCP Cursor IDE Hooks

Enforce SCP skill contracts in [Cursor IDE](https://cursor.com) using the hooks system.

## How It Works

Cursor hooks allow you to run scripts before/after agent events. SCP uses three hooks:

| Hook | Event | Purpose | failClosed |
|------|-------|---------|------------|
| `scp-session.py` | `sessionStart` | Detect active skill from user message | No |
| `scp-enforcer.py` | `preToolUse` | Gate tool calls against contract's `tool_ids` | **Yes** |
| `scp-evidence.py` | `postToolUse` | Detect evidence from tool results via regex | No |

### Enforcement Flow

```
User message → sessionStart hook → detect skill contract
                                 → persist SessionState to /tmp/scp-session-{pid}.json

Tool call → preToolUse hook → load state → build enforcer
                            → check tool against tool_ids (+ delegation merges)
                            → APPROVE or REJECT

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

## Evidence Detection

Evidence can be automatically detected from tool outputs using regex rules defined in the contract:

```yaml
constraints:
  evidence:
    required:
      - id: slack_thread_read
        description: "Slack thread content retrieved"
      - id: alert_classified
        description: "Alert classified by ownership"
    detection:
      - evidence_id: slack_thread_read
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

Skills can delegate to child skills using `delegates_to`:

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
      description: Delegate to investigation skill
      delegates: ecp-traffic-alert-investigation
```

During delegation, the child contract's `tool_ids` are merged with the parent's allowed set, enabling the agent to use investigation-specific tools without the parent contract blocking them.

## Limitations

### L1: Reasoning-step evidence

Evidence that requires LLM reasoning (e.g., "correctly identified root cause") cannot be verified deterministically by hooks. These must remain prose-based instructions in the skill's markdown body.

### L2: Skill activation detection

Cursor hooks receive limited context about which skill is active. The `sessionStart` hook infers activation from:
1. Slash commands in the initial message (e.g., `/slack-alert-reader`)
2. Keyword triggers defined in the contract's `activation.triggers`

If the agent is invoked without a clear trigger, the hooks operate in pass-through mode (all tools allowed).

## State File

Session state is stored at `/tmp/scp-session-{pid}.json`:

```json
{
  "active_skill_path": "/home/user/.cursor/skills/slack-alert-reader/SKILL.md",
  "collected_evidence": ["slack_thread_read"],
  "delegation_stack": [],
  "iteration": 2
}
```

The file is created on session start and updated after each tool call. It is automatically cleaned up when the process exits.
