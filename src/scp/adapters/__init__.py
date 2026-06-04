"""Adapters for bridging SCP contracts to external systems."""

from .cursor_hook import (
    SessionState,
    handle_post_tool_use,
    handle_pre_tool_use,
    handle_session_start,
    load_state,
    save_state,
)
from .elastic import from_elastic_payload, to_elastic_payload
from .prompt import build_system_prompt

__all__ = [
    "SessionState",
    "build_system_prompt",
    "from_elastic_payload",
    "handle_post_tool_use",
    "handle_pre_tool_use",
    "handle_session_start",
    "load_state",
    "save_state",
    "to_elastic_payload",
]
