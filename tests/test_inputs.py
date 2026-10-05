"""Tests for declared inputs: the model, scp.runtime.inputs and the validator rules."""

import pytest
from pydantic import ValidationError

from scp.loader import load_skill_from_string
from scp.models import Constraints, InputSpec, PlanStep, SkillContract
from scp.runtime import declared_inputs, resolve_inputs
from scp.validator import validate_contract


def _contract(inputs: list[InputSpec] | None = None, *templates: dict[str, object]) -> SkillContract:
    return SkillContract(
        scp="1.0",
        name="test",
        description="Test.",
        inputs=inputs,
        constraints=Constraints(
            plan=[PlanStep(tool="query", description="Q", args_template=t) for t in templates] or None
        ),
    )


_HOST_TEMPLATE: dict[str, object] = {"host": "{{host_id}}", "nested": {"q": "region={{region}}"}}


class TestModel:
    def test_placeholders_are_collected_from_every_step(self) -> None:
        contract = _contract(None, _HOST_TEMPLATE, {"items": ["{{alert_time}}", "{{host_id}}"]})

        assert contract.placeholders == ["alert_time", "host_id", "region"]

    def test_input_defaults(self) -> None:
        spec = InputSpec(name="host_id", description="Host.")

        assert spec.required is True
        assert spec.pattern is None

    @pytest.mark.parametrize("name", ["", "1host", "host-id", "host id"])
    def test_input_name_must_be_a_placeholder_identifier(self, name: str) -> None:
        with pytest.raises(ValidationError):
            InputSpec(name=name, description="x")

    def test_loads_from_frontmatter(self) -> None:
        contract = load_skill_from_string(
            "---\nscp: '1.0'\nname: t\ndescription: T\n"
            "inputs:\n  - name: host_id\n    description: Host\n    required: false\n    pattern: 'i-\\w+'\n---\n"
        )

        assert contract.inputs == [InputSpec(name="host_id", description="Host", required=False, pattern=r"i-\w+")]


class TestDeclaredInputs:
    def test_uses_the_inputs_block(self) -> None:
        inputs = [InputSpec(name="host_id", description="Host.")]

        assert declared_inputs(_contract(inputs, _HOST_TEMPLATE)) == inputs

    def test_falls_back_to_required_placeholders(self) -> None:
        specs = declared_inputs(_contract(None, _HOST_TEMPLATE))

        assert [(s.name, s.required, s.pattern) for s in specs] == [("host_id", True, None), ("region", True, None)]


class TestResolveInputs:
    def test_accepts_matching_values(self) -> None:
        contract = _contract([InputSpec(name="host_id", description="Host.", pattern=r"i-[0-9a-f]+")])

        resolution = resolve_inputs(contract, {"host_id": " i-0abc ", "unknown": "ignored"})

        assert resolution.ok
        assert resolution.values == {"host_id": "i-0abc"}

    def test_reports_missing_required_inputs(self) -> None:
        contract = _contract(
            [InputSpec(name="host_id", description="Host."), InputSpec(name="note", description="N.", required=False)]
        )

        resolution = resolve_inputs(contract, {"host_id": "  ", "note": None})

        assert resolution.missing == ["host_id"]
        assert resolution.values == {}

    def test_pattern_must_match_the_whole_value(self) -> None:
        contract = _contract([InputSpec(name="host_id", description="Host.", pattern=r"i-[0-9a-f]+")])

        resolution = resolve_inputs(contract, {"host_id": "i-0abc; rm -rf /"})

        assert resolution.invalid == ["host_id"]
        assert resolution.values == {}
        assert not resolution.ok

    def test_without_an_inputs_block_every_placeholder_is_required(self) -> None:
        resolution = resolve_inputs(_contract(None, _HOST_TEMPLATE), {"host_id": "i-1"})

        assert resolution.values == {"host_id": "i-1"}
        assert resolution.missing == ["region"]


class TestValidator:
    def test_declared_inputs_cover_every_placeholder(self) -> None:
        inputs = [InputSpec(name="host_id", description="H."), InputSpec(name="region", description="R.")]

        assert validate_contract(_contract(inputs, _HOST_TEMPLATE)) == []

    def test_undeclared_placeholder_is_an_error(self) -> None:
        errors = validate_contract(_contract([InputSpec(name="host_id", description="H.")], _HOST_TEMPLATE))

        assert errors == ["Placeholder '{{region}}' is not declared in inputs"]

    def test_no_inputs_block_skips_the_placeholder_check(self) -> None:
        assert validate_contract(_contract(None, _HOST_TEMPLATE)) == []

    def test_unused_declared_input_is_allowed(self) -> None:
        assert validate_contract(_contract([InputSpec(name="ticket", description="T.")])) == []

    def test_duplicate_input_names(self) -> None:
        inputs = [InputSpec(name="host_id", description="A."), InputSpec(name="host_id", description="B.")]

        assert validate_contract(_contract(inputs)) == ["Duplicate input name: 'host_id'"]

    def test_invalid_pattern(self) -> None:
        errors = validate_contract(_contract([InputSpec(name="host_id", description="H.", pattern="i-(")]))

        assert len(errors) == 1
        assert errors[0].startswith("inputs['host_id'].pattern is not a valid regex")
