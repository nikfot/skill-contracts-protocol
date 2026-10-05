"""Resolve host-supplied values for a contract's declared inputs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from ..models import InputSpec, SkillContract


@dataclass
class InputResolution:
    """Outcome of ``resolve_inputs``. ``values`` holds only the accepted values."""

    values: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.invalid


def declared_inputs(contract: SkillContract) -> list[InputSpec]:
    """The contract's inputs; without an ``inputs`` block, each placeholder is a required input."""
    if contract.inputs is not None:
        return list(contract.inputs)
    return [InputSpec(name=name, description=name) for name in contract.placeholders]


def resolve_inputs(contract: SkillContract, values: Mapping[str, str | None]) -> InputResolution:
    """Check ``values`` against the declared inputs.

    Blank values count as absent. A required input that is absent is ``missing``; a value
    that does not fully match its ``pattern`` is ``invalid`` and is left out of ``values``.
    Keys that are not declared inputs are ignored.
    """
    resolution = InputResolution()
    for spec in declared_inputs(contract):
        value = (values.get(spec.name) or "").strip()
        if not value:
            if spec.required:
                resolution.missing.append(spec.name)
        elif spec.pattern is not None and re.fullmatch(spec.pattern, value) is None:
            resolution.invalid.append(spec.name)
        else:
            resolution.values[spec.name] = value
    return resolution
