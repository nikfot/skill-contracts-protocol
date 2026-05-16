"""Tests for Activation metadata and exclusive activation semantics."""

from scp.models import Activation, SkillContract


class TestActivation:
    def test_defaults(self) -> None:
        a = Activation()
        assert a.triggers is None
        assert a.slash_command is None
        assert a.attachment_types is None
        assert a.auto_discover is True

    def test_full_activation(self) -> None:
        a = Activation(
            triggers=["latency", "p99"],
            slash_command="investigate-latency",
            attachment_types=["alert"],
            auto_discover=True,
        )
        assert a.triggers == ["latency", "p99"]
        assert a.slash_command == "investigate-latency"
        assert a.attachment_types == ["alert"]


class TestEffectiveTriggers:
    def test_activation_triggers(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="act",
            description="Test.",
            activation=Activation(triggers=["x", "y"]),
        )
        assert contract.effective_triggers == ["x", "y"]

    def test_no_activation_empty_triggers(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="none",
            description="Test.",
        )
        assert contract.effective_triggers == []

    def test_activation_without_triggers(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="no-trig",
            description="Test.",
            activation=Activation(slash_command="my-skill"),
        )
        assert contract.effective_triggers == []


class TestExclusiveActivation:
    """The exclusive activation model: no activation = always discoverable,
    activation present = invocable only through declared routes."""

    def test_no_activation_always_discoverable(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="passive",
            description="Test.",
        )
        assert contract.is_always_discoverable is True
        assert contract.is_auto_discoverable is True

    def test_activation_present_not_always_discoverable(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="active",
            description="Test.",
            activation=Activation(triggers=["latency"]),
        )
        assert contract.is_always_discoverable is False
        assert contract.is_auto_discoverable is True

    def test_auto_discover_disabled(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="exclusive",
            description="Test.",
            activation=Activation(
                triggers=["latency"],
                auto_discover=False,
            ),
        )
        assert contract.is_always_discoverable is False
        assert contract.is_auto_discoverable is False

    def test_slash_command_only(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="slash",
            description="Test.",
            activation=Activation(slash_command="my-skill"),
        )
        assert contract.activation is not None
        assert contract.activation.slash_command == "my-skill"
        assert contract.is_always_discoverable is False

    def test_attachment_types(self) -> None:
        contract = SkillContract(
            scp="1.0",
            name="attach",
            description="Test.",
            activation=Activation(attachment_types=["alert", "case"]),
        )
        assert contract.activation is not None
        assert contract.activation.attachment_types == ["alert", "case"]

    def test_load_from_frontmatter(self) -> None:
        from scp.loader import load_skill_from_string

        text = """\
---
scp: "1.0"
name: with-activation
description: Has activation metadata.
activation:
  triggers: [latency, slo]
  slash_command: investigate
  attachment_types: [alert]
  auto_discover: true
---

# Skill body
"""
        contract = load_skill_from_string(text)
        assert contract.activation is not None
        assert contract.activation.slash_command == "investigate"
        assert contract.activation.triggers == ["latency", "slo"]
        assert contract.activation.attachment_types == ["alert"]
        assert contract.is_always_discoverable is False
        assert contract.is_auto_discoverable is True
