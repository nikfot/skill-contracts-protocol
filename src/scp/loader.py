"""Load SCP contracts from SKILL.md, YAML, or JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import frontmatter

from .models import SkillContract


def load_skill(path: str | Path) -> SkillContract:
    """Parse a SKILL.md, YAML, or JSON file into a SkillContract.

    Supports:
    - Markdown files with YAML frontmatter (``---`` delimiters)
    - Plain YAML files (treated as frontmatter-only, no body)
    - JSON files (must contain an ``scp`` key)

    Raises ``ValueError`` if the file lacks an ``scp`` key or
    fails validation.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    if path.suffix == ".json":
        return load_skill_from_json(text)

    return load_skill_from_string(text)


def load_skill_from_string(text: str) -> SkillContract:
    """Parse a skill contract from a raw string.

    Accepts both frontmatter-bearing markdown and plain YAML.
    """
    post = frontmatter.loads(text)
    metadata: dict[str, Any] = dict(post.metadata)

    if "scp" not in metadata:
        raise ValueError("Missing 'scp' key in frontmatter -- not an SCP file.")

    body = str(post.content).strip()
    metadata["content"] = body
    return SkillContract.model_validate(metadata)


def load_skill_from_json(text: str) -> SkillContract:
    """Parse a skill contract from a JSON string.

    The JSON object must contain an ``scp`` key. An optional
    ``content`` key is used as the Markdown body.
    """
    data: dict[str, Any] = json.loads(text)
    return load_skill_from_dict(data, content=data.get("content", ""))


def load_skill_from_dict(data: dict[str, Any], content: str = "") -> SkillContract:
    """Build a SkillContract from an already-parsed dict.

    Useful when consuming skill metadata from an HTTP API or JSON file
    rather than a SKILL.md file on disk.
    """
    if "scp" not in data:
        raise ValueError("Missing 'scp' key -- not an SCP contract.")

    merged = {**data, "content": content}
    return SkillContract.model_validate(merged)
