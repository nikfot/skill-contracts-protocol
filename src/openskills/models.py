"""Pydantic models for OpenSkills v1.0 skill contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class EvidenceItem(BaseModel):
    """A single piece of evidence the agent must collect."""

    id: str = Field(min_length=1, pattern=r"^[a-z_][a-z0-9_]*$")
    description: str = Field(min_length=1)


class PlanStep(BaseModel):
    """An ordered step in the skill's query plan."""

    tool: str = Field(min_length=1)
    description: str = Field(min_length=1)
    args_template: dict[str, Any] | None = None


class EvidenceRequirements(BaseModel):
    """Evidence the agent must collect before finalization."""

    required: list[EvidenceItem] = Field(min_length=1)

    @field_validator("required")
    @classmethod
    def unique_evidence_ids(cls, v: list[EvidenceItem]) -> list[EvidenceItem]:
        ids = [item.id for item in v]
        if len(ids) != len(set(ids)):
            dupes = [eid for eid in ids if ids.count(eid) > 1]
            raise ValueError(f"Duplicate evidence IDs: {sorted(set(dupes))}")
        return v


class FinalizationRules(BaseModel):
    """Rules governing when the agent may produce its final output."""

    require_all_evidence: bool = True
    min_iterations: int = Field(default=0, ge=0)


class ReferencedContent(BaseModel):
    """A named supplementary content block the agent can consult selectively."""

    name: str = Field(min_length=1)
    path: str = Field(default="", description="Relative path hint (e.g. ``./queries``).")
    content: str = Field(default="", description="Inline Markdown content.")
    required: bool = Field(default=False, description="If true, the agent must consult this block before finalizing.")


class Constraints(BaseModel):
    """The enforcement contract for a skill."""

    allowed_tools: list[str] | None = None
    plan: list[PlanStep] | None = None
    evidence: EvidenceRequirements | None = None
    finalization: FinalizationRules | None = None
    tool_overrides: dict[str, str] | None = None
    referenced_content: list[ReferencedContent] | None = None


class SkillContract(BaseModel):
    """A fully parsed OpenSkills v1.0 skill contract."""

    openskills: str = Field(pattern=r"^1\.0$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    triggers: list[str] | None = None
    constraints: Constraints | None = None
    content: str = Field(default="", description="Markdown body after frontmatter.")

    @property
    def allowed_tools(self) -> set[str] | None:
        """Tool whitelist, or None if unconstrained."""
        if self.constraints and self.constraints.allowed_tools is not None:
            return set(self.constraints.allowed_tools)
        return None

    @property
    def plan_steps(self) -> list[PlanStep]:
        """Ordered plan steps, empty if no plan defined."""
        if self.constraints and self.constraints.plan:
            return self.constraints.plan
        return []

    @property
    def required_evidence(self) -> list[EvidenceItem]:
        """Required evidence items, empty if none defined."""
        if self.constraints and self.constraints.evidence:
            return self.constraints.evidence.required
        return []

    @property
    def finalization(self) -> FinalizationRules:
        """Finalization rules, defaults if not specified."""
        if self.constraints and self.constraints.finalization:
            return self.constraints.finalization
        return FinalizationRules()

    @property
    def tool_overrides(self) -> dict[str, str]:
        """Tool alias mapping, empty if not defined."""
        if self.constraints and self.constraints.tool_overrides:
            return self.constraints.tool_overrides
        return {}

    @property
    def referenced_content(self) -> list[ReferencedContent]:
        """Referenced content blocks, empty if none defined."""
        if self.constraints and self.constraints.referenced_content:
            return self.constraints.referenced_content
        return []

    def resolve_tool(self, name: str) -> str:
        """Resolve a tool name through overrides."""
        return self.tool_overrides.get(name, name)

    def is_tool_allowed(self, name: str) -> bool:
        """Check if a tool is permitted by the contract."""
        allowed = self.allowed_tools
        if allowed is None:
            return True
        resolved = self.resolve_tool(name)
        return resolved in allowed or name in allowed
