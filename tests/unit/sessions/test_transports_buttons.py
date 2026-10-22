"""Tests for the persistent button transport."""

from types import SimpleNamespace

import pytest

from juliabot.sessions import (
    Action,
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    Session,
    SessionManager,
    TriggerType,
)
from juliabot.sessions.transports.buttons import (
    SessionButtonView,
    build_button_view,
    build_custom_id,
    parse_custom_id,
)


class ButtonSession(Session):
    actions = (
        Action("next", "next_page", owner_only=False, label="Next", style="primary"),
        Action("delete", "delete_message", emoji="x", style="danger"),
    )

    async def next_page(self, event: InteractionEvent) -> None:
        self.set_payload("next_user", event.user_id)

    async def delete_message(self, event: InteractionEvent) -> None:
        await self.close()


def make_manager():
    registry = Registry()
    registry.register(
        Registration(
            name="buttons",
            session_class=ButtonSession,
            trigger=TriggerType.COMPONENT,
            scope=Scope.CHANNEL,
        )
    )
    return SessionManager(registry)


def make_interaction(user_id: int, message_id: int = 55):
    class Response:
        def __init__(self):
            self.actions = []

        def is_done(self):
            return bool(self.actions)

        async def defer(self):
            self.actions.append(("defer",))

        async def send_message(self, content, ephemeral=False):
            self.actions.append(("send_message", content, ephemeral))

    response = Response()
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        guild=SimpleNamespace(id=10),
        channel=SimpleNamespace(id=20),
        message=SimpleNamespace(id=message_id),
        response=response,
    )
    return interaction


@pytest.mark.asyncio
async def test_view_builds_persistent_buttons_with_stable_ids():
    manager = make_manager()
    session = await manager.start(
        "buttons",
        InteractionEvent(
            transport=TriggerType.COMPONENT,
            key="message-55",
            user_id=1,
            guild_id=10,
            channel_id=20,
            message_id=55,
        ),
    )

    view = build_button_view(manager, session)

    assert isinstance(view, SessionButtonView)
    assert view.timeout is None
    assert [button.custom_id for button in view.children] == [
        f"sess:{session.id}:next",
        f"sess:{session.id}:delete",
    ]
    assert view.children[0].label == "Next"


@pytest.mark.asyncio
async def test_button_callback_dispatches_and_acknowledges_interaction():
    manager = make_manager()
    session = await manager.start(
        "buttons",
        InteractionEvent(
            transport=TriggerType.COMPONENT,
            key="message-55",
            user_id=1,
            channel_id=20,
            message_id=55,
        ),
    )
    button = build_button_view(manager, session).children[0]
    interaction = make_interaction(user_id=2)

    await button.callback(interaction)

    assert session.to_payload()["next_user"] == 2
    assert interaction.response.actions == [("defer",)]


@pytest.mark.asyncio
async def test_button_callback_reports_owner_denial_ephemerally():
    manager = make_manager()
    session = await manager.start(
        "buttons",
        InteractionEvent(
            transport=TriggerType.COMPONENT,
            key="message-55",
            user_id=1,
            channel_id=20,
            message_id=55,
        ),
    )
    button = build_button_view(manager, session).children[1]
    interaction = make_interaction(user_id=2)

    await button.callback(interaction)

    assert interaction.response.actions == [
        ("send_message", "Você não pode usar esta ação.", True)
    ]


def test_custom_id_round_trip_and_length_limit():
    custom_id = build_custom_id("a" * 80, "next")

    assert parse_custom_id(custom_id) == ("a" * 80, "next")

    with pytest.raises(ValueError, match="100-character"):
        build_custom_id("a" * 95, "next")

    with pytest.raises(ValueError, match="Invalid"):
        parse_custom_id("other:id:next")
