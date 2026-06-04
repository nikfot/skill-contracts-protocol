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

### 1. Install the SCP library

```bash
pip install skill-contracts-protocol
# or from source:
pip install -e /path/to/skill-contracts-protocol
```

### 2. Configure skill directories

Set the `SCP_SKILL_DIRS` environment variable to point to directories containing SKILL.md files with SCP contracts:

```bash
export SCP_SKILL_DIRS="$HOME/.cursor/skills:$(pwd)/.cursor/skills"
```

### 3. Add hooks to your project

Copy `hooks.json` to `.cursor/hooks.json` in your project (or merge with existing hooks):

```bash
cp examples/cursor-ide/hooks/hooks.json /path/to/project/.cursor/hooks.json
```

Adjust the script paths in `hooks.json` to point to where the hook scripts are installed.

### 4. Alternative: Global installation via symlinks

```bash
# From the SCP repo root:
HOOKS_DIR="$HOME/.cursor/hooks"
mkdir -p "$HOOKS_DIR"
ln -sf "$(pwd)/examples/cursor-ide/hooks/scp-enforcer.py" "$HOOKS_DIR/"
ln -sf "$(pwd)/examples/cursor-ide/hooks/scp-evidence.py" "$HOOKS_DIR/"
ln -sf "$(pwd)/examples/cursor-ide/hooks/scp-session.py" "$HOOKS_DIR/"
```

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
