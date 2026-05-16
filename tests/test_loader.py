"""Tests for openskills.loader."""

from pathlib import Path

import pytest

from openskills.loader import load_skill, load_skill_from_dict, load_skill_from_string
from openskills.models import SkillContract

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "spec" / "examples"


class TestLoadSkillFromString:
    def test_full_frontmatter(self) -> None:
        text = """\
---
openskills: "1.0"
name: test-skill
description: A test skill.
constraints:
  allowed_tools:
    - tool_a
  evidence:
    required:
      - id: data_ok
        description: Data is present.
---

# Test Skill

Body content here.
"""
        contract = load_skill_from_string(text)
        assert contract.name == "test-skill"
        assert contract.allowed_tools == {"tool_a"}
        assert len(contract.required_evidence) == 1
        assert "Body content" in contract.content

    def test_no_constraints(self) -> None:
        text = """\
---
openskills: "1.0"
name: simple
description: No constraints.
---

Just markdown.
"""
        contract = load_skill_from_string(text)
        assert contract.constraints is None
        assert contract.is_tool_allowed("anything") is True

    def test_missing_openskills_key(self) -> None:
        text = """\
---
name: bad
description: No openskills key.
---
"""
        with pytest.raises(ValueError, match="openskills"):
            load_skill_from_string(text)


class TestLoadSkillFromDict:
    def test_from_api_response(self) -> None:
        data = {
            "openskills": "1.0",
            "name": "api-skill",
            "description": "From API.",
            "constraints": {
                "allowed_tools": ["query"],
            },
        }
        contract = load_skill_from_dict(data, content="# From API")
        assert isinstance(contract, SkillContract)
        assert contract.content == "# From API"

    def test_missing_openskills_key(self) -> None:
        with pytest.raises(ValueError, match="openskills"):
            load_skill_from_dict({"name": "bad"})


class TestLoadSkillFromFile:
    def test_full_constraints_example(self) -> None:
        path = EXAMPLES_DIR / "full-constraints.yaml"
        if not path.exists():
            pytest.skip("Example file not found")
        contract = load_skill(path)
        assert contract.name == "investigate-proxy-latency"
        assert contract.allowed_tools is not None
        assert "run_es_query" in contract.allowed_tools
        assert len(contract.plan_steps) == 3
        assert len(contract.required_evidence) == 5
        assert contract.finalization.min_iterations == 1

    def test_no_constraints_example(self) -> None:
        path = EXAMPLES_DIR / "no-constraints.yaml"
        if not path.exists():
            pytest.skip("Example file not found")
        contract = load_skill(path)
        assert contract.name == "general-troubleshooting"
        assert contract.constraints is None

    def test_partial_constraints_example(self) -> None:
        path = EXAMPLES_DIR / "partial-constraints.yaml"
        if not path.exists():
            pytest.skip("Example file not found")
        contract = load_skill(path)
        assert contract.name == "check-service-health"
        assert contract.plan_steps == []
        assert len(contract.required_evidence) == 2

    def test_args_template_example(self) -> None:
        path = EXAMPLES_DIR / "args-template.yaml"
        if not path.exists():
            pytest.skip("Example file not found")
        contract = load_skill(path)
        assert contract.plan_steps[0].args_template is not None
        assert "{{node_name}}" in str(contract.plan_steps[0].args_template["query"])

    def test_multi_evidence_example(self) -> None:
        path = EXAMPLES_DIR / "multi-evidence.yaml"
        if not path.exists():
            pytest.skip("Example file not found")
        contract = load_skill(path)
        assert len(contract.required_evidence) == 5
        assert contract.finalization.min_iterations == 2

    def test_referenced_content_example(self) -> None:
        path = EXAMPLES_DIR / "referenced-content.yaml"
        if not path.exists():
            pytest.skip("Example file not found")
        contract = load_skill(path)
        assert len(contract.referenced_content) == 2
        assert contract.referenced_content[0].name == "queries"
        assert contract.referenced_content[1].required is True
