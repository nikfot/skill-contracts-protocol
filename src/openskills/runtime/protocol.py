"""Data types for runtime tool-call handling.

Extracted and generalized from elastic/sophia's SkillRuntime protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolRewrite:
    """Outcome of a tool-call enforcement decision."""

    tool_name: str
    tool_args: dict[str, Any]
    rewritten: bool = False
    blocked: bool = False
    block_reason: str | None = None


@dataclass
class ToolCallResult:
    """Normalized result from a tool invocation.

    The runtime doesn't care how the tool was called -- only what came back.
    Consumers populate this from their framework-specific tool response.
    """

    tool_name: str
    tool_args: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
