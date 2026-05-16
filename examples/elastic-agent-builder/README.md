# Elastic Agent Builder Integration

This example shows how to convert an OpenSkills contract into an
[Elastic Agent Builder](https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/skills)
skill payload and push it via the Kibana REST API.

## Files

- `skill.md` -- An OpenSkills skill with constraints (YAML frontmatter + Markdown)
- `convert_and_push.py` -- Converts the skill to an Elastic payload and optionally
  pushes it to Kibana

## Usage

```bash
# Convert to JSON (stdout)
python convert_and_push.py

# Push to Kibana
KIBANA_URL=https://your-kibana API_KEY=your-key python convert_and_push.py --push
```
