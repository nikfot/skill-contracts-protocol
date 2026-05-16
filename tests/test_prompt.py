"""Tests for openskills.adapters.prompt."""

from openskills.adapters.prompt import build_system_prompt
from openskills.models import (
    Constraints,
    EvidenceItem,
    EvidenceRequirements,
    FinalizationRules,
    PlanStep,
    SkillContract,
)


class TestBuildSystemPrompt:
    def test_no_constraints(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="open",
            description="No constraints.",
        )
        prompt = build_system_prompt(contract)
        assert "open" in prompt
        assert "operate freely" in prompt

    def test_full_contract(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="full-skill",
            description="Full featured skill.",
            constraints=Constraints(
                tool_ids=["query", "report"],
                plan=[
                    PlanStep(tool="query", description="Fetch data"),
                    PlanStep(tool="report", description="Generate report"),
                ],
                evidence=EvidenceRequirements(
                    required=[
                        EvidenceItem(id="data_ok", description="Data fetched"),
                        EvidenceItem(id="report_ok", description="Report generated"),
                    ]
                ),
                finalization=FinalizationRules(
                    require_all_evidence=True,
                    min_iterations=2,
                ),
                tool_overrides={"search": "query"},
            ),
        )
        prompt = build_system_prompt(contract)
        assert "## Skill: full-skill" in prompt
        assert "query" in prompt
        assert "report" in prompt
        assert "ONLY use these tools" in prompt
        assert "search" in prompt
        assert "Fetch data" in prompt
        assert "data_ok" in prompt
        assert "report_ok" in prompt
        assert "2" in prompt
        assert "Do NOT finalize" in prompt

    def test_exclude_plan(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="no-plan-prompt",
            description="Plan excluded.",
            constraints=Constraints(
                plan=[PlanStep(tool="a", description="Step A")],
            ),
        )
        prompt = build_system_prompt(contract, include_plan=False)
        assert "Investigation Plan" not in prompt

    def test_tool_ids_only(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="tools-only",
            description="Just tools.",
            constraints=Constraints(
                tool_ids=["alpha", "beta"],
            ),
        )
        prompt = build_system_prompt(contract)
        assert "alpha" in prompt
        assert "beta" in prompt
        assert "ONLY use these tools" in prompt
        assert "Required Evidence" not in prompt

    def test_evidence_only(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="evidence-only",
            description="Just evidence.",
            constraints=Constraints(
                evidence=EvidenceRequirements(
                    required=[EvidenceItem(id="check", description="Check done")]
                ),
            ),
        )
        prompt = build_system_prompt(contract)
        assert "check" in prompt
        assert "Allowed Tools" not in prompt

    def test_args_template_in_plan(self) -> None:
        contract = SkillContract(
            openskills="1.0",
            name="with-args",
            description="Plan with args.",
            constraints=Constraints(
                plan=[
                    PlanStep(
                        tool="query",
                        description="Fetch",
                        args_template={"q": "{{domain}}"},
                    )
                ],
            ),
        )
        prompt = build_system_prompt(contract)
        assert "{{domain}}" in prompt
