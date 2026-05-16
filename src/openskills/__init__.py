"""OpenSkills -- declarative skill contracts for LLM agents."""

__version__ = "0.1.0"

from .loader import load_skill, load_skill_from_dict, load_skill_from_json, load_skill_from_string
from .models import (
    Activation,
    Constraints,
    EvidenceItem,
    EvidenceRequirements,
    FinalizationRules,
    PlanStep,
    SkillContract,
)

__all__ = [
    "Activation",
    "Constraints",
    "EvidenceItem",
    "EvidenceRequirements",
    "FinalizationRules",
    "PlanStep",
    "SkillContract",
    "load_skill",
    "load_skill_from_dict",
    "load_skill_from_json",
    "load_skill_from_string",
]
