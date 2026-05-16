"""Load OpenSkills contracts from SKILL.md files or raw YAML/dict."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter

from .models import SkillContract


def load_skill(path: str | Path) -> SkillContract:
    """Parse a SKILL.md (or .yaml) file into a SkillContract.

    Supports:
    - Markdown files with YAML frontmatter (``---`` delimiters)
    - Plain YAML files (treated as frontmatter-only, no body)

    Raises ``ValueError`` if the file lacks an ``openskills`` key or
    fails validation.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return load_skill_from_string(text)


def load_skill_from_string(text: str) -> SkillContract:
    """Parse a skill contract from a raw string.

    Accepts both frontmatter-bearing markdown and plain YAML.
    """
    post = frontmatter.loads(text)
    metadata: dict[str, Any] = dict(post.metadata)

    if "openskills" not in metadata:
        raise ValueError("Missing 'openskills' key in frontmatter -- not an OpenSkills file.")

    body = str(post.content).strip()
    metadata["content"] = body
    return SkillContract.model_validate(metadata)


def load_skill_from_dict(data: dict[str, Any], content: str = "") -> SkillContract:
    """Build a SkillContract from an already-parsed dict.

    Useful when consuming skill metadata from an HTTP API or JSON file
    rather than a SKILL.md file on disk.
    """
    if "openskills" not in data:
        raise ValueError("Missing 'openskills' key -- not an OpenSkills contract.")

    merged = {**data, "content": content}
    return SkillContract.model_validate(merged)
