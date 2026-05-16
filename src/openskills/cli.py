"""CLI entry point: openskills validate <file|dir>."""

from __future__ import annotations

import sys
from pathlib import Path

import click
import frontmatter

from .loader import load_skill_from_string
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
                contract = load_skill_from_string(text)
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


def _collect_files(paths: tuple[str, ...]) -> list[Path]:
    """Expand directories and filter to supported file types."""
    suffixes = {".yaml", ".yml", ".md"}
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
