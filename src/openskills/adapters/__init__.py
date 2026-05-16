"""Adapters for bridging OpenSkills contracts to external systems."""

from .elastic import from_elastic_payload, to_elastic_payload
from .prompt import build_system_prompt

__all__ = ["build_system_prompt", "from_elastic_payload", "to_elastic_payload"]
