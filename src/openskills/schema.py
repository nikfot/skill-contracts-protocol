"""JSON Schema loading and validation for OpenSkills contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema


_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "spec" / "openskills-schema.json"


@lru_cache(maxsize=1)
def get_schema() -> dict[str, Any]:
    """Load and cache the OpenSkills JSON Schema."""
    text = _SCHEMA_PATH.read_text(encoding="utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema


def validate_against_schema(data: dict[str, Any]) -> list[str]:
    """Validate a dict against the OpenSkills JSON Schema.

    Returns a list of error messages. Empty list means valid.
    """
    schema = get_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"{path}: {error.message}")
    return errors
