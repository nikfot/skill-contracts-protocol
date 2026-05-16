# OpenSkills in a Python Application

This example shows how to use the `openskills` library to enforce skill
contracts inside your own agent loop. No specific LLM SDK is required --
the runtime works with any tool-calling framework.

## What This Demonstrates

1. **Load** a skill contract from a SKILL.md file or a dict
2. **Execute** plan steps deterministically with template interpolation
3. **Track** evidence as tool results come back
4. **Gate** finalization until all evidence is collected
5. **Build** a system prompt from the contract for your LLM

## Files

- `agent_loop.py` -- Complete working example of an agent loop with
  OpenSkills enforcement. Simulates tool calls with mock responses.
- `skill.yaml` -- The skill contract used by the example.

## Running the Example

```bash
# From the repo root:
uv run python examples/python-app/agent_loop.py

# Or with pip:
pip install openskills
python examples/python-app/agent_loop.py
```

## How It Works

```
                    ┌─────────────┐
                    │ Load Skill  │
                    │ (YAML file) │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Build Prompt│ ─── inject into LLM system message
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
              ┌────►│ Plan Step?  │
              │     └──────┬──────┘
              │        yes │    no (plan exhausted)
              │     ┌──────▼──────┐     │
              │     │ Check Tool  │     │
              │     │ (enforcer)  │     │
              │     └──────┬──────┘     │
              │     blocked│   ok       │
              │       ▼    │            │
              │     skip   │            │
              │            │            │
              │     ┌──────▼──────┐     │
              │     │ Execute Tool│◄────┘
              │     └──────┬──────┘
              │            │
              │     ┌──────▼──────┐
              │     │Record Result│
              │     │ (evidence)  │
              │     └──────┬──────┘
              │            │
              │     ┌──────▼──────┐
              │  no │Can Finalize?│
              └─────┤ (enforcer)  │
                    └──────┬──────┘
                       yes │
                    ┌──────▼──────┐
                    │  Finalize   │
                    └─────────────┘
```

## Adapting to Your Framework

The example uses mock tool responses. In a real application, replace
`simulate_tool_call()` with your actual tool execution:

- **LangGraph**: Call the tool node and feed results back
- **PydanticAI**: Use the tool decorator and capture results
- **CrewAI**: Wrap as a CrewAI tool and record evidence
- **Custom**: Call any HTTP API, CLI, or SDK

The OpenSkills runtime doesn't care how tools are called -- it only
cares about what came back and whether the evidence requirements are met.
