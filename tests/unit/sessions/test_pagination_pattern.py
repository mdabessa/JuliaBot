"""Tests for the reusable PaginationSession pattern."""

from types import SimpleNamespace

import pytest

from juliabot.sessions import (
    Action,
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)
from juliabot.sessions.patterns import PaginationSession


class FakeMessage:
    def __init__(self):
        self.edits = []
        self.deleted = False

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeContext:
    def __init__(self):
        self.messages = []

    async def reply(self, **kwargs):
        message = FakeMessage()
        message.initial = kwargs
        self.messages.append(message)
        return message


class NumberPagination(PaginationSession[int]):
    extra_actions = (Action("delete", "delete_current"),)

    def __init__(self, *args, source=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = list([1, 2, 3] if source is None else source)
        self.deleted = []

    async def load_items(self):
        return self.source

    async def render_item(self, item, index, total):
        return {"item": item, "index": index, "total": total}

    async def delete_item(self, item, event):
        self.deleted.append(item)
        return True


def registration():
    return Registration(
        name="numbers",
        session_class=NumberPagination,
        trigger=TriggerType.COMPONENT,
        scope=Scope.USER,
    )


def event(context, key="message-1", action=None):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=key,
        user_id=1,
        channel_id=20,
        message_id=55,
        action=action,
        raw=context,
    )


def make_manager():
    registry = Registry()
    registry.register(registration())
    return SessionManager(registry)


@pytest.mark.asyncio
async def test_pagination_starts_at_zero_and_wraps_pages():
    context = FakeContext()
    manager = make_manager()
    session = await manager.start("numbers", event(context))

    assert session.index == 0
    assert context.messages[0].initial["embed"] == {
        "item": 1,
        "index": 0,
        "total": 3,
    }

    await manager.dispatch(event(context, action="previous"))
    assert session.index == 2
    await manager.dispatch(event(context, action="next"))
    assert session.index == 0
    assert len(session._message.edits) == 2


@pytest.mark.asyncio
async def test_pagination_empty_source_closes_without_message():
    context = FakeContext()
    manager = make_manager()
    session = NumberPagination(
        registration(), event(context), payload={"index": 0}, source=[]
    )
    session.manager = manager
    await session.start(event(context))

    assert session.closed is True
    assert context.messages == []


@pytest.mark.asyncio
async def test_pagination_delete_mutates_items_and_closes_when_empty():
    context = FakeContext()
    manager = make_manager()
    session = await manager.start("numbers", event(context))

    await manager.dispatch(event(context, action="delete"))

    assert session.deleted == [1]
    assert session.items == (2, 3)
    assert session.index == 0

    session._items = [2]
    await manager.dispatch(event(context, action="delete"))

    assert session.closed is True
    assert session._message.edits[-1] == {
        "content": "Não há itens para exibir.",
        "embed": None,
    }


@pytest.mark.asyncio
async def test_pagination_supports_progressive_append_and_refresh():
    context = FakeContext()
    manager = make_manager()
    session = NumberPagination(
        registration(), event(context), payload={"index": 0}, source=[]
    )
    session.manager = manager
    await session.append_item(10)

    assert session.items == (10,)
    assert session.index == 0

    session.source = [10, 20, 30]
    await session.refresh_items()

    assert session.items == (10, 20, 30)
    assert session.index == 0
    assert session._message is None
