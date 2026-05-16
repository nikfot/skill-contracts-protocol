# Elastic Agent Builder Integration

This example shows how to convert between OpenSkills contracts (used by
Cursor IDE skills, Claude Code, and other LLM agent frameworks) and
[Elastic Agent Builder](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/skills)
skill payloads.

## Files

| File | Direction | Description |
|------|-----------|-------------|
| `skill.md` | — | An OpenSkills skill with constraints (YAML frontmatter + Markdown) |
| `convert_and_push.py` | OpenSkills → Kibana | Convert a skill and optionally push via the Kibana API |
| `cursor_to_kibana.py` | Cursor → Kibana | Convert an existing Cursor SKILL.md into a Kibana payload |
| `kibana_to_cursor.py` | Kibana → Cursor | Convert a Kibana skill JSON into a Cursor-compatible SKILL.md |

## Cursor SKILL.md → Kibana Agent Builder

Take any OpenSkills-enhanced Cursor skill and deploy it to Kibana:

```bash
# Convert the included Cursor IDE example
python cursor_to_kibana.py ../cursor-ide/investigate-latency/SKILL.md
```

This reads the YAML frontmatter, extracts `allowed_tools` → `tool_ids`,
serialises the constraints as an enforcement preamble in the `content`
field, and prints the JSON payload you'd send to
`POST /api/agent_builder/skills`.

### What happens during conversion

| Cursor SKILL.md field | Elastic API field | Notes |
|----------------------|-------------------|-------|
| `name` | `id`, `name` | Used as the skill identifier |
| `description` | `description` | Triggers appended if present |
| `constraints.allowed_tools` | `tool_ids` | Sorted alphabetically |
| `constraints.plan` | (injected into `content`) | Rendered as "Investigation Plan" |
| `constraints.evidence` | (injected into `content`) | Rendered as "Required Evidence" |
| `constraints.finalization` | (injected into `content`) | Rendered as "Finalization Rules" |
| Markdown body | `content` (after preamble) | Preserved verbatim |

## Kibana Agent Builder → Cursor SKILL.md

Import an existing Kibana skill as a Cursor SKILL.md:

```bash
# Use the built-in example
python kibana_to_cursor.py

# Or convert from a JSON file
python kibana_to_cursor.py my-kibana-skill.json
```

The script converts `tool_ids` → `constraints.allowed_tools` and
preserves the `content` as the Markdown body. Plan steps, evidence, and
finalization rules are not inferred from prose -- add them manually to
get runtime enforcement.

### What you get vs. what you need to add

| Feature | Automatically converted | Needs manual addition |
|---------|------------------------|-----------------------|
| Tool whitelist | Yes (`tool_ids` → `allowed_tools`) | — |
| Markdown instructions | Yes (`content` preserved) | — |
| Plan steps | — | Yes (define `constraints.plan`) |
| Evidence gates | — | Yes (define `constraints.evidence`) |
| Finalization rules | — | Yes (define `constraints.finalization`) |

## Direct push to Kibana

```bash
# Convert to JSON (stdout)
python convert_and_push.py

# Push to Kibana
KIBANA_URL=https://your-kibana API_KEY=your-key python convert_and_push.py --push
```
