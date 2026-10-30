"""Behavior tests for the generated route pagination session."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from discord import Embed

from juliabot import jikan_catalog as catalog
from juliabot import jikan_sessions as sessions_module
from juliabot.sessions import InteractionEvent, Registry, SessionManager, TriggerType


class FakeJikan:
    """Page-aware Jikan double returning anime-shaped pages."""

    def __init__(self, pages=None, has_next=None):
        self.pages = pages or {}
        self.has_next = has_next or {}
        self.calls: list[tuple[str, dict]] = []

    async def get_top_anime(self, **kwargs):
        page = kwargs.get("page", 1)
        self.calls.append(("get_top_anime", kwargs))
        has_next = self.has_next.get(page, page < max(self.pages, default=1))
        return SimpleNamespace(
            data=[
                {
                    "mal_id": item,
                    "title": f"Anime {item}",
                    "url": f"https://x/{item}",
                    "score": 9.0,
                }
                for item in self.pages.get(page, [])
            ],
            pagination=SimpleNamespace(has_next_page=has_next, current_page=page),
        )


class FakeMessage:
    def __init__(self, channel, content=None, embed=None, view=None):
        self.channel = channel
        self.content = content
        self.embed = embed
        self.view = view
        self.edits = []

    async def edit(self, content=None, embed=None, view=None):
        self.embed = embed
        self.edits.append((content, embed))


class FakeChannel:
    async def send(self, content=None, **_kwargs):
        return None


class FakeContext:
    def __init__(self, bot):
        self.bot = bot
        self.channel = FakeChannel()
        self.replied = []

    async def reply(self, content=None, embed=None, view=None):
        message = FakeMessage(self.channel, content, embed, view)
        self.replied.append(message)
        return message


def make_context(jikan):
    bot = SimpleNamespace(color=0xE6DC56, jikan=jikan)
    return FakeContext(bot)


def make_manager():
    manager = SessionManager(Registry())
    sessions_module.register(manager)
    return manager


def start_event(context, key="msg-1", user_id=7):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=key,
        user_id=user_id,
        guild_id=10,
        channel_id=20,
        message_id=55,
        raw=context,
    )


def action_event(session, action, user_id=7):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=session.id,
        user_id=user_id,
        action=action,
    )


def payload(**overrides):
    base = {
        "route": "get_top_anime",
        "kwargs": {"type": "tv"},
        "api_page": 1,
        "index": 0,
        "has_next": False,
    }
    base.update(overrides)
    return base


def test_register_is_idempotent():
    manager = make_manager()
    first = manager.registry.get(sessions_module.JIKAN_PAGE)

    sessions_module.register(manager)

    assert manager.registry.get(sessions_module.JIKAN_PAGE) is first
    assert first.session_class is sessions_module.JikanRoutePagination
    assert first.resumable is True


def test_route_spec_lookup():
    assert sessions_module.route_spec("get_top_anime") is not None
    assert sessions_module.route_spec("get_nonexistent") is None


@pytest.mark.asyncio
async def test_start_renders_the_first_result_with_buttons():
    jikan = FakeJikan({1: [1, 2]})
    context = make_context(jikan)
    manager = make_manager()

    session = await manager.start(
        sessions_module.JIKAN_PAGE, start_event(context), payload=payload()
    )

    assert jikan.calls == [("get_top_anime", {"type": "tv", "page": 1})]
    assert len(context.replied) == 1
    message = context.replied[0]
    assert isinstance(message.embed, Embed)
    assert message.embed.title == "Anime 1"
    assert message.embed.footer.text == "top_anime • 1/2"
    assert message.view is not None
    assert [action.name for action in session.actions] == ["previous", "next"]


@pytest.mark.asyncio
async def test_next_walks_the_loaded_page_before_fetching_another():
    jikan = FakeJikan({1: [1, 2], 2: [3]})
    context = make_context(jikan)
    manager = make_manager()
    session = await manager.start(
        sessions_module.JIKAN_PAGE, start_event(context), payload=payload()
    )

    await session.next_page(action_event(session, "next"))
    assert session.index == 1
    assert jikan.calls[-1] == ("get_top_anime", {"type": "tv", "page": 1})

    await session.next_page(action_event(session, "next"))
    assert jikan.calls[-1] == ("get_top_anime", {"type": "tv", "page": 2})
    assert session.index == 0
    assert session.to_payload()["api_page"] == 2
    assert context.replied[0].embed.title == "Anime 3"


@pytest.mark.asyncio
async def test_previous_at_the_start_of_page_two_loads_page_one():
    jikan = FakeJikan({1: [1, 2], 2: [3]})
    context = make_context(jikan)
    manager = make_manager()
    session = await manager.start(
        sessions_module.JIKAN_PAGE,
        start_event(context),
        payload=payload(api_page=2, index=0),
    )

    await session.previous_page(action_event(session, "previous"))

    assert session.to_payload()["api_page"] == 1
    assert session.index == 1
    assert context.replied[0].embed.title == "Anime 2"


@pytest.mark.asyncio
async def test_next_stops_at_the_last_api_page():
    jikan = FakeJikan({1: [1]}, has_next={1: False})
    context = make_context(jikan)
    manager = make_manager()
    session = await manager.start(
        sessions_module.JIKAN_PAGE, start_event(context), payload=payload()
    )
    calls_before = list(jikan.calls)

    await session.next_page(action_event(session, "next"))

    assert jikan.calls == calls_before
    assert session.index == 0


@pytest.mark.asyncio
async def test_previous_on_the_first_page_of_page_one_does_nothing():
    jikan = FakeJikan({1: [1]})
    context = make_context(jikan)
    manager = make_manager()
    session = await manager.start(
        sessions_module.JIKAN_PAGE, start_event(context), payload=payload()
    )
    calls_before = list(jikan.calls)

    await session.previous_page(action_event(session, "previous"))

    assert jikan.calls == calls_before
    assert session.index == 0


@pytest.mark.asyncio
async def test_api_failure_while_loading_another_page_keeps_the_current_one():
    jikan = FakeJikan({1: [1]})
    context = make_context(jikan)
    manager = make_manager()
    session = await manager.start(
        sessions_module.JIKAN_PAGE, start_event(context), payload=payload()
    )
    session.set_payload("has_next", True)

    async def boom(**_kwargs):
        raise sessions_module.JikanCallError("A API está instável agora.")

    jikan.get_top_anime = boom

    moved = await session.load_more(1)

    assert moved is False
    assert session.to_payload()["api_page"] == 1
    assert session.index == 0


@pytest.mark.asyncio
async def test_empty_api_page_is_not_navigated_into():
    jikan = FakeJikan({1: [1]})
    context = make_context(jikan)
    manager = make_manager()
    session = await manager.start(
        sessions_module.JIKAN_PAGE, start_event(context), payload=payload()
    )
    session.set_payload("has_next", True)

    moved = await session.load_more(1)

    assert moved is False
    assert session.to_payload()["api_page"] == 1


@pytest.mark.asyncio
async def test_an_unknown_route_closes_the_session(monkeypatch):
    monkeypatch.setitem(sessions_module.specs_by_route(), "get_top_anime", None)
    sessions_module.specs_by_route.cache_clear()
    context = make_context(FakeJikan({1: [1]}))
    manager = make_manager()

    try:
        session = await manager.start(
            sessions_module.JIKAN_PAGE,
            start_event(context),
            payload=payload(route="get_ghost"),
        )
        assert session.closed
        assert context.replied == []
    finally:
        sessions_module.specs_by_route.cache_clear()


@pytest.mark.asyncio
async def test_payload_is_json_safe_and_resumable():
    jikan = FakeJikan({1: [1, 2]}, has_next={1: True})
    context = make_context(jikan)
    manager = make_manager()
    session = await manager.start(
        sessions_module.JIKAN_PAGE,
        start_event(context),
        payload=payload(kwargs={"type": "tv", "limit": 5}),
    )

    state = session.to_payload()

    assert json.loads(json.dumps(state)) == state
    catalog.load_specs()  # the route name is a real catalog key
    assert state == {
        "route": "get_top_anime",
        "kwargs": {"type": "tv", "limit": 5},
        "api_page": 1,
        "index": 0,
        "has_next": True,
    }


@pytest.mark.asyncio
async def test_the_initial_page_can_be_chosen_with_the_page_argument():
    jikan = FakeJikan({2: [9]})
    context = make_context(jikan)
    manager = make_manager()

    session = await manager.start(
        sessions_module.JIKAN_PAGE,
        start_event(context),
        payload=payload(api_page=2),
    )

    assert jikan.calls == [("get_top_anime", {"type": "tv", "page": 2})]
    assert not session.closed
    assert context.replied[0].embed.title == "Anime 9"
