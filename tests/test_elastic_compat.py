"""Tests for Elastic Agent Builder compatibility checks."""

from pathlib import Path

from click.testing import CliRunner

from openskills.cli import main
from openskills.elastic_compat import validate_elastic_compatibility
from openskills.models import Constraints, SkillContract


def _make_contract(**kwargs: object) -> SkillContract:
    defaults: dict[str, object] = {
        "openskills": "1.0",
        "name": "test-skill",
        "description": "Test skill. Use when testing.",
    }
    return SkillContract(**{**defaults, **kwargs})  # type: ignore[arg-type]


class TestValidateElasticCompatibility:
    def test_valid_contract(self) -> None:
        contract = _make_contract()
        assert validate_elastic_compatibility(contract) == []

    def test_name_too_long(self) -> None:
        contract = _make_contract(name="a" * 65)
        issues = validate_elastic_compatibility(contract)
        assert any("64-char" in i for i in issues)

    def test_description_too_long(self) -> None:
        contract = _make_contract(description="x" * 1025 + " Use when testing.")
        issues = validate_elastic_compatibility(contract)
        assert any("1024-char" in i for i in issues)

    def test_missing_use_when(self) -> None:
        contract = _make_contract(description="No routing clause here.")
        issues = validate_elastic_compatibility(contract)
        assert any("Use when" in i for i in issues)

    def test_use_this_accepted(self) -> None:
        contract = _make_contract(description="Use this when errors spike.")
        assert validate_elastic_compatibility(contract) == []

    def test_too_many_tools(self) -> None:
        tools = [f"platform.core.tool_{i}" for i in range(101)]
        contract = _make_contract(constraints=Constraints(tool_ids=tools))
        issues = validate_elastic_compatibility(contract)
        assert any("100-tool" in i for i in issues)

    def test_unknown_namespace(self) -> None:
        contract = _make_contract(
            constraints=Constraints(tool_ids=["custom.my_tool"]),
        )
        issues = validate_elastic_compatibility(contract)
        assert any("custom" in i for i in issues)

    def test_valid_namespaces(self) -> None:
        contract = _make_contract(
            constraints=Constraints(
                tool_ids=["platform.core.search", "security.alerts"]
            ),
        )
        assert validate_elastic_compatibility(contract) == []

    def test_non_dotted_tools_ok(self) -> None:
        contract = _make_contract(
            constraints=Constraints(tool_ids=["run_query"]),
        )
        assert validate_elastic_compatibility(contract) == []


class TestCLIElasticCheck:
    def test_compatible_file(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("good.yaml").write_text(
                "---\n"
                "openskills: '1.0'\n"
                "name: good-skill\n"
                "description: A good skill. Use when testing.\n"
                "---\n"
            )
            result = runner.invoke(main, ["elastic-check", "good.yaml"])
            assert result.exit_code == 0
            assert "elastic-compatible" in result.output

    def test_incompatible_file(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("bad.yaml").write_text(
                "---\n"
                "openskills: '1.0'\n"
                "name: bad-skill\n"
                "description: No routing clause.\n"
                "---\n"
            )
            result = runner.invoke(main, ["elastic-check", "bad.yaml"])
            assert result.exit_code == 1
            assert "Use when" in result.output

    def test_multiple_issues(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("multi.yaml").write_text(
                "---\n"
                "openskills: '1.0'\n"
                f"name: {'a' * 70}\n"
                "description: No clause.\n"
                "---\n"
            )
            result = runner.invoke(main, ["elastic-check", "multi.yaml"])
            assert result.exit_code == 1
            assert "64-char" in result.output
            assert "Use when" in result.output
