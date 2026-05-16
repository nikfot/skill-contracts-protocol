"""Tests for openskills.cli."""

from pathlib import Path

from click.testing import CliRunner

from openskills.cli import main

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "spec" / "examples"


class TestCLIValidate:
    def test_valid_examples_directory(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["validate", str(EXAMPLES_DIR)])
        assert result.exit_code == 0
        assert "error(s)" in result.output
        assert "0 error(s)" in result.output

    def test_single_valid_file(self) -> None:
        runner = CliRunner()
        path = EXAMPLES_DIR / "full-constraints.yaml"
        result = runner.invoke(main, ["validate", str(path)])
        assert result.exit_code == 0
        assert "ok" in result.output

    def test_invalid_file(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("bad.yaml").write_text(
                "---\nopenskills: '1.0'\nname: ''\ndescription: Valid\n---\n"
            )
            result = runner.invoke(main, ["validate", "bad.yaml"])
            assert result.exit_code == 1

    def test_non_openskills_file_skipped(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("plain.yaml").write_text("---\nname: not-openskills\n---\n")
            result = runner.invoke(main, ["validate", "plain.yaml"])
            assert "0 file(s) checked" in result.output

    def test_referential_integrity_error(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("ref-err.yaml").write_text(
                "---\n"
                "openskills: '1.0'\n"
                "name: ref-test\n"
                "description: Ref integrity test\n"
                "constraints:\n"
                "  allowed_tools:\n"
                "    - tool_a\n"
                "  plan:\n"
                "    - tool: tool_b\n"
                "      description: Wrong tool\n"
                "---\n"
            )
            result = runner.invoke(main, ["validate", "ref-err.yaml"])
            assert result.exit_code == 1
            assert "tool_b" in result.output

    def test_version_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
