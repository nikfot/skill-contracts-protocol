"""Tests for JSON loading and CLI convert command."""

import json
from pathlib import Path

from click.testing import CliRunner

from scp.cli import main
from scp.loader import load_skill, load_skill_from_json


class TestLoadSkillFromJson:
    def test_basic_json(self) -> None:
        text = json.dumps({
            "scp": "1.0",
            "name": "json-skill",
            "description": "From JSON.",
            "content": "# Hello\n\nBody.",
        })
        contract = load_skill_from_json(text)
        assert contract.name == "json-skill"
        assert "Body" in contract.content

    def test_json_with_constraints(self) -> None:
        text = json.dumps({
            "scp": "1.0",
            "name": "constrained-json",
            "description": "Constraints in JSON.",
            "constraints": {
                "tool_ids": ["tool_a"],
            },
        })
        contract = load_skill_from_json(text)
        assert contract.tool_ids == {"tool_a"}


class TestLoadSkillJsonFile:
    def test_load_json_file(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "skill.json"
        skill_file.write_text(json.dumps({
            "scp": "1.0",
            "name": "file-json",
            "description": "From file.",
            "content": "Body.",
        }))
        contract = load_skill(skill_file)
        assert contract.name == "file-json"


class TestCLIConvert:
    def test_yaml_to_json(self, tmp_path: Path) -> None:
        src = tmp_path / "skill.yaml"
        src.write_text(
            "---\nscp: '1.0'\nname: convert-test\n"
            "description: Test conversion.\n---\n"
        )
        dst = tmp_path / "skill.json"
        runner = CliRunner()
        result = runner.invoke(main, ["convert", str(src), str(dst)])
        assert result.exit_code == 0
        data = json.loads(dst.read_text())
        assert data["name"] == "convert-test"

    def test_json_to_md(self, tmp_path: Path) -> None:
        src = tmp_path / "skill.json"
        src.write_text(json.dumps({
            "scp": "1.0",
            "name": "to-md",
            "description": "Convert to MD.",
            "content": "# Heading\n\nBody.",
        }))
        dst = tmp_path / "skill.md"
        runner = CliRunner()
        result = runner.invoke(main, ["convert", str(src), str(dst)])
        assert result.exit_code == 0
        text = dst.read_text()
        assert "---" in text
        assert "to-md" in text
        assert "# Heading" in text

    def test_md_to_json(self, tmp_path: Path) -> None:
        src = tmp_path / "skill.md"
        src.write_text(
            "---\nscp: '1.0'\nname: md-to-json\n"
            "description: Round trip.\n---\n\n# Content\n"
        )
        dst = tmp_path / "output.json"
        runner = CliRunner()
        result = runner.invoke(main, ["convert", str(src), str(dst)])
        assert result.exit_code == 0
        data = json.loads(dst.read_text())
        assert data["name"] == "md-to-json"
        assert "Content" in data.get("content", "")

    def test_validate_json_file(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "valid.json"
        skill_file.write_text(json.dumps({
            "scp": "1.0",
            "name": "json-validate",
            "description": "Validate JSON.",
        }))
        runner = CliRunner()
        result = runner.invoke(main, ["validate", str(skill_file)])
        assert result.exit_code == 0
        assert "1 file(s) checked" in result.output
        assert "0 error(s)" in result.output
