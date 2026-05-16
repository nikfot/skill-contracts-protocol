# Examples

Two integration examples showing how SCP adds value in practice.

## 1. Cursor IDE (`cursor-ide/`)

Drop an SCP-enhanced SKILL.md into your Cursor project and get
structured agent behavior -- tool guardrails, an investigation plan, and
evidence gates -- without writing any code.

**What you get:** The agent follows a deterministic plan, only uses
approved tools, and cannot finalize until all required evidence is
collected. Today's SKILL.md files only describe *what* to do; SCP
adds *how to stay on track*.

## 2. Python Application (`python-app/`)

Use the `scp` library in your own agent loop to enforce skill
contracts programmatically. Load a skill, execute its plan, track
evidence, gate finalization, and build system prompts -- all without
coupling to a specific LLM SDK.

**What you get:** A reusable enforcement layer you can drop into
LangGraph, PydanticAI, CrewAI, or any custom agent loop.
