"""Tests for openskills.adapters.elastic."""

from pathlib import Path

from openskills import load_skill
from openskills.adapters.elastic import from_elastic_payload, to_elastic_payload
from openskills.models import (
    Constraints,
    EvidenceItem,
    EvidenceRequirements,
    FinalizationRules,
    PlanStep,
    SkillContract,
)

CURSOR_EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "cursor-ide" / "investigate-latency" / "SKILL.md"


def _full_contract() -> SkillContract:
    return SkillContract(
        openskills="1.0",
        name="investigate-latency",
        description="Investigate service latency spikes.",
        triggers=["latency", "p99"],
        constraints=Constraints(
            allowed_tools=["platform.core.execute_esql", "platform.core.search"],
            plan=[
                PlanStep(
                    tool="platform.core.execute_esql",
                    description="Fetch raw latency data",
                    args_template={"query": "FROM heartbeat-* | LIMIT 100"},
                ),
            ],
            evidence=EvidenceRequirements(
                required=[
                    EvidenceItem(id="data_presence", description="Data exists"),
                    EvidenceItem(id="latency_stats", description="Percentiles computed"),
                ]
            ),
            finalization=FinalizationRules(require_all_evidence=True, min_iterations=1),
        ),
        content="# Investigate Latency\n\nMarkdown body here.",
    )


class TestToElasticPayload:
    def test_basic_fields(self) -> None:
        payload = to_elastic_payload(_full_contract())
        assert payload["id"] == "investigate-latency"
        assert payload["name"] == "investigate-latency"
        assert "latency" in payload["description"]
        assert "Triggers:" in payload["description"]

    def test_tool_ids_sorted(self) -> None:
        payload = to_elastic_payload(_full_contract())
        assert payload["tool_ids"] == [
            "platform.core.execute_esql",
            "platform.core.search",
        ]

    def test_content_includes_enforcement_preamble(self) -> None:
        payload = to_elastic_payload(_full_contract(), inject_constraints=True)
        content = payload["content"]
        assert "Allowed Tools" in content
        assert "Required Evidence" in content
        assert "Finalization Rules" in content
        assert "Markdown body here" in content

    def test_content_without_injection(self) -> None:
        payload = to_elastic_payload(_full_contract(), inject_constraints=False)
        content = payload["content"]
        assert "Allowed Tools" not in content
        assert "Markdown body here" in content

    def test_no_constraints(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="simple-skill",
            description="No constraints.",
            content="Just markdown.",
        )
        payload = to_elastic_payload(contract)
        assert "tool_ids" not in payload
        assert "Just markdown" in payload["content"]

    def test_description_truncated_at_1024(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="long-desc",
            description="x" * 2000,
        )
        payload = to_elastic_payload(contract)
        assert len(payload["description"]) <= 1024

    def test_no_triggers(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="no-triggers",
            description="Plain description.",
        )
        payload = to_elastic_payload(contract)
        assert "Triggers:" not in payload["description"]
        assert payload["description"] == "Plain description."


class TestFromElasticPayload:
    def test_basic_round_trip(self) -> None:
        elastic_payload = {
            "id": "my-log-triage",
            "name": "Log Triage",
            "description": "Triage log errors.",
            "content": "## Steps\n\n1. Query errors",
            "tool_ids": [
                "platform.core.execute_esql",
                "platform.core.generate_esql",
            ],
        }
        contract = from_elastic_payload(elastic_payload)
        assert contract.name == "my-log-triage"
        assert contract.description == "Triage log errors."
        assert contract.content == "## Steps\n\n1. Query errors"
        assert contract.allowed_tools == {
            "platform.core.execute_esql",
            "platform.core.generate_esql",
        }

    def test_no_tool_ids(self) -> None:
        contract = from_elastic_payload({
            "id": "bare",
            "name": "bare",
            "description": "No tools.",
        })
        assert contract.constraints is None
        assert contract.allowed_tools is None

    def test_empty_tool_ids(self) -> None:
        contract = from_elastic_payload({
            "id": "empty-tools",
            "name": "empty-tools",
            "description": "Empty tools list.",
            "tool_ids": [],
        })
        assert contract.constraints is None

    def test_uses_id_over_name(self) -> None:
        contract = from_elastic_payload({
            "id": "the-id",
            "name": "The Display Name",
            "description": "Test.",
        })
        assert contract.name == "the-id"

    def test_fallback_to_name_when_no_id(self) -> None:
        contract = from_elastic_payload({
            "name": "fallback-name",
            "description": "Test.",
        })
        assert contract.name == "fallback-name"


class TestRoundTrip:
    def test_contract_survives_round_trip(self) -> None:
        original = _full_contract()
        payload = to_elastic_payload(original, inject_constraints=False)
        restored = from_elastic_payload(payload)

        assert restored.name == original.name
        assert restored.allowed_tools == original.allowed_tools
        assert original.content in restored.content


class TestCursorToKibanaSmoke:
    """End-to-end smoke tests using the real Cursor IDE example."""

    def test_cursor_skill_loads_and_converts(self) -> None:
        if not CURSOR_EXAMPLE.exists():
            import pytest
            pytest.skip("Cursor example not found")

        contract = load_skill(CURSOR_EXAMPLE)
        payload = to_elastic_payload(contract, inject_constraints=True)

        assert payload["id"] == "investigate-latency"
        assert isinstance(payload["tool_ids"], list)
        assert len(payload["tool_ids"]) > 0
        assert "run_es_query" in payload["tool_ids"]
        assert "Investigate Service Latency" in payload["content"]
        assert "Allowed Tools" in payload["content"]
        assert "Investigation Plan" in payload["content"]
        assert "Required Evidence" in payload["content"]

    def test_cursor_skill_round_trips_through_kibana(self) -> None:
        if not CURSOR_EXAMPLE.exists():
            import pytest
            pytest.skip("Cursor example not found")

        contract = load_skill(CURSOR_EXAMPLE)
        payload = to_elastic_payload(contract, inject_constraints=False)
        restored = from_elastic_payload(payload)

        assert restored.name == contract.name
        assert restored.allowed_tools == contract.allowed_tools
        assert contract.content in restored.content
