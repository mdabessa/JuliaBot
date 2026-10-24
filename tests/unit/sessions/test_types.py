"""Tests for framework value types."""

from juliabot.sessions import Action, InteractionEvent, Scope, TriggerType


def test_trigger_and_scope_values_are_stable_strings():
    assert TriggerType.MESSAGE.value == "message"
    assert TriggerType.REACTION.value == "reaction"
    assert TriggerType.COMPONENT.value == "component"
    assert Scope.NONE.value == "none"
    assert Scope.USER.value == "user"
    assert Scope.GUILD.value == "guild"
    assert Scope.CHANNEL.value == "channel"


def test_action_defaults_to_registration_ownership():
    action = Action(name="next", handler="next_page")

    assert action.owner_only is None
    assert action.label is None
    assert action.emoji is None


def test_interaction_event_contains_transport_context():
    event = InteractionEvent(
        transport=TriggerType.COMPONENT,
        key="session-1",
        user_id=42,
        action="next",
        channel_id=7,
    )

    assert event.key == "session-1"
    assert event.user_id == 42
    assert event.channel_id == 7
