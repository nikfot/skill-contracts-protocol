# Examples

Three integration examples showing how SCP adds value in practice.

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

## 3. Autonomous Agent (`autonomous-agent/`)

The core SCP use case: an agent that runs **without human supervision**
(remote MCP server, background worker, webhook handler) and needs a
machine-readable definition of done. The contract prevents premature
finalization, blocks destructive tool calls, and forces thorough evidence
collection before the agent can declare the investigation complete.

**What you get:** A pattern for any agent that runs in a loop and must
keep going until an explicit result is reached -- not just "good enough."
