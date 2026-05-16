"""CLI entry point: openskills validate/convert."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import frontmatter
import yaml

from .elastic_compat import validate_elastic_compatibility
from .loader import load_skill, load_skill_from_string
from .schema import validate_against_schema
from .validator import validate_contract


@click.group()
@click.version_option()
def main() -> None:
    """OpenSkills -- declarative skill contracts for LLM agents."""


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
def validate(paths: tuple[str, ...]) -> None:
    """Validate skill files against the OpenSkills v1.0 spec.

    Accepts files (.yaml, .yml, .md) or directories (scanned recursively).
    """
    files = _collect_files(paths)
    if not files:
        click.echo("No skill files found.", err=True)
        sys.exit(1)

    total_errors = 0
    checked = 0

    for path in sorted(files):
        text = path.read_text(encoding="utf-8")

        if path.suffix == ".json":
            try:
                metadata = json.loads(text)
            except json.JSONDecodeError as exc:
                click.echo(f"\n{path}:")
                click.echo(f"  - JSON parse error: {exc}")
                total_errors += 1
                continue
        else:
            post = frontmatter.loads(text)
            metadata = dict(post.metadata)

        if "openskills" not in metadata:
            continue

        checked += 1
        file_errors: list[str] = []

        schema_errors = validate_against_schema(metadata)
        file_errors.extend(schema_errors)

        if not schema_errors:
            try:
                contract = load_skill(path)
                ref_errors = validate_contract(contract)
                file_errors.extend(ref_errors)
            except Exception as exc:
                file_errors.append(f"Parse error: {exc}")

        if file_errors:
            click.echo(f"\n{path}:")
            for err in file_errors:
                click.echo(f"  - {err}")
            total_errors += len(file_errors)
        else:
            click.echo(f"  {path}: ok")

    click.echo(f"\n{checked} file(s) checked, {total_errors} error(s).")
    sys.exit(1 if total_errors > 0 else 0)


@main.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path())
def convert(input_path: str, output_path: str) -> None:
    """Convert a skill between YAML/Markdown and JSON formats.

    The output format is inferred from the output file extension:
    - .json -> serialize as JSON
    - .md   -> serialize as SKILL.md with YAML frontmatter
    - .yaml/.yml -> serialize as plain YAML
    """
    contract = load_skill(input_path)
    out = Path(output_path)

    if out.suffix == ".json":
        data = contract.model_dump(exclude_none=True, exclude={"content"})
        if contract.content:
            data["content"] = contract.content
        out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    elif out.suffix == ".md":
        data = contract.model_dump(exclude_none=True, exclude={"content"})
        fm = yaml.dump(data, default_flow_style=False, sort_keys=False).strip()
        body = contract.content or ""
        out.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")
    elif out.suffix in {".yaml", ".yml"}:
        data = contract.model_dump(exclude_none=True, exclude={"content"})
        text = yaml.dump(data, default_flow_style=False, sort_keys=False)
        out.write_text(f"---\n{text}---\n", encoding="utf-8")
    else:
        click.echo(f"Unsupported output format: {out.suffix}", err=True)
        sys.exit(1)

    click.echo(f"Converted {input_path} -> {output_path}")


@main.command("elastic-check")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
def elastic_check(paths: tuple[str, ...]) -> None:
    """Check skill files for Elastic Agent Builder compatibility.

    Validates name length (64 chars), description length (1024 chars),
    tool count limits (100), description quality ('Use when...' clause),
    and tool namespace conventions.
    """
    files = _collect_files(paths)
    if not files:
        click.echo("No skill files found.", err=True)
        sys.exit(1)

    total_issues = 0
    checked = 0

    for path in sorted(files):
        text = path.read_text(encoding="utf-8")
        post = frontmatter.loads(text)
        metadata = dict(post.metadata)

        if "openskills" not in metadata:
            continue

        checked += 1

        try:
            contract = load_skill_from_string(text)
        except Exception as exc:
            click.echo(f"\n{path}:")
            click.echo(f"  - Parse error: {exc}")
            total_issues += 1
            continue

        issues = validate_elastic_compatibility(contract)

        if issues:
            click.echo(f"\n{path}:")
            for issue in issues:
                click.echo(f"  - {issue}")
            total_issues += len(issues)
        else:
            click.echo(f"  {path}: elastic-compatible")

    click.echo(f"\n{checked} file(s) checked, {total_issues} issue(s).")
    sys.exit(1 if total_issues > 0 else 0)


def _collect_files(paths: tuple[str, ...]) -> list[Path]:
    """Expand directories and filter to supported file types."""
    suffixes = {".yaml", ".yml", ".md", ".json"}
    result: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix in suffixes:
            result.append(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix in suffixes:
                    result.append(child)
    return result
