"""Behavior tests for the migrated anime sessions."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from discord import Embed

from juliabot.cogs import animes as animes_module
from juliabot.sessions import (
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)


class FakeJikan:
    """Minimal Jikan double with page-aware search results."""

    def __init__(self, pages=None):
        self.pages = pages or {}
        self.calls = []

    async def search_anime(self, search_type, query, page=1):
        self.calls.append(page)
        return SimpleNamespace(
            data=list(self.pages.get(page, [])),
            pagination=SimpleNamespace(
                has_next_page=page < max(self.pages) if self.pages else False,
                current_page=page,
            ),
        )

    async def get_anime(self, mal_id):
        return SimpleNamespace(mal_id=mal_id, title=f"Anime {mal_id}")


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **_kwargs):
        self.sent.append(content)


class FakeMessage:
    def __init__(self, channel, content=None, embed=None, view=None):
        self.channel = channel
        self.content = content
        self.embed = embed
        self.view = view
        self.edits = []

    async def edit(self, content=None, embed=None):
        self.edits.append((content, embed))


class FakeContext:
    def __init__(self, bot, cog):
        self.bot = bot
        self.cog = cog
        self.channel = FakeChannel()
        self.replied = []

    async def reply(self, content=None, embed=None, view=None):
        message = FakeMessage(self.channel, content, embed, view)
        self.replied.append(message)
        return message


class FakeRow:
    def __init__(self, mal_id, user_id, dubbed=False):
        self.mal_id = mal_id
        self.user_id = user_id
        self.dubbed = dubbed
        self.deleted = False

    def delete(self):
        self.deleted = True


def anime(mal_id):
    return SimpleNamespace(mal_id=mal_id, title=f"Anime {mal_id}")


def simple_embed(item, _color):
    return Embed(title=item.title)


def make_manager(session_class, name):
    registry = Registry()
    registry.register(
        Registration(
            name=name,
            session_class=session_class,
            trigger=TriggerType.COMPONENT,
            scope=Scope.USER,
            timeout=300,
        )
    )
    return SessionManager(registry)


def make_context(jikan):
    bot = SimpleNamespace(color=0xE6DC56, jikan=jikan)
    return FakeContext(bot, SimpleNamespace(jikan=jikan))


def start_event(context, key="command-1", user_id=7):
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


@pytest.mark.asyncio
async def test_search_loads_next_jikan_page_at_boundary(monkeypatch):
    monkeypatch.setattr(animes_module, "anime_embed", simple_embed)
    jikan = FakeJikan({1: [anime(1), anime(2)], 2: [anime(3)]})
    context = make_context(jikan)
    manager = make_manager(
        animes_module.AnimeSearchPagination, animes_module.ANIME_SEARCH
    )
    session = await manager.start(
        animes_module.ANIME_SEARCH,
        start_event(context),
        payload={"query": "frieren", "jikan_page": 1, "dubbed": False},
    )

    await manager.dispatch(action_event(session, "next"))
    assert session.index == 1

    await manager.dispatch(action_event(session, "next"))

    assert session.index == 0
    assert jikan.calls == [1, 2]
    assert session.to_payload()["jikan_page"] == 2
    assert context.replied[0].edits[-1][1].title == "Anime 3"


@pytest.mark.asyncio
async def test_search_with_no_results_closes_without_a_message(monkeypatch):
    monkeypatch.setattr(animes_module, "anime_embed", simple_embed)
    context = make_context(FakeJikan({1: []}))
    manager = make_manager(
        animes_module.AnimeSearchPagination, animes_module.ANIME_SEARCH
    )

    session = await manager.start(
        animes_module.ANIME_SEARCH,
        start_event(context),
        payload={"query": "missing", "jikan_page": 1, "dubbed": False},
    )

    assert session.closed is True
    assert manager.active() == ()
    assert context.replied == []


@pytest.mark.asyncio
async def test_search_wraps_within_page_when_no_next_page(monkeypatch):
    monkeypatch.setattr(animes_module, "anime_embed", simple_embed)
    jikan = FakeJikan({1: [anime(1), anime(2)]})
    context = make_context(jikan)
    manager = make_manager(
        animes_module.AnimeSearchPagination, animes_module.ANIME_SEARCH
    )
    session = await manager.start(
        animes_module.ANIME_SEARCH,
        start_event(context),
        payload={"query": "frieren", "jikan_page": 1, "dubbed": False},
    )

    await manager.dispatch(action_event(session, "next"))
    await manager.dispatch(action_event(session, "next"))

    assert session.index == 0
    assert jikan.calls == [1]


@pytest.mark.asyncio
async def test_search_add_action_creates_watchlist_entry(monkeypatch):
    monkeypatch.setattr(animes_module, "anime_embed", simple_embed)
    created = []

    class FakeListModel:
        @staticmethod
        def get(**_kwargs):
            return None

        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr(animes_module, "AnimesList", FakeListModel)
    context = make_context(FakeJikan({1: [anime(1)]}))
    manager = make_manager(
        animes_module.AnimeSearchPagination, animes_module.ANIME_SEARCH
    )
    session = await manager.start(
        animes_module.ANIME_SEARCH,
        start_event(context),
        payload={"query": "frieren", "jikan_page": 1, "dubbed": True},
    )

    assert await manager.dispatch(action_event(session, "add", user_id=42)) is True

    assert created == [{"user_id": 42, "mal_id": 1, "dubbed": True}]
    assert context.channel.sent[-1] == "`Anime 1 (Dublado)` adicionado a lista!"


@pytest.mark.asyncio
async def test_anime_list_delete_requires_entry_owner(monkeypatch):
    monkeypatch.setattr(animes_module, "anime_embed", simple_embed)
    row = FakeRow(mal_id=1, user_id="7")
    monkeypatch.setattr(animes_module.AnimesList, "get_user", lambda user_id: [row])
    context = make_context(FakeJikan())
    manager = make_manager(animes_module.AnimeListPagination, animes_module.ANIME_LIST)
    session = await manager.start(
        animes_module.ANIME_LIST,
        start_event(context),
        payload={"target_user_id": 7},
    )
    await session.wait_for_loading()

    await manager.dispatch(action_event(session, "delete", user_id=8))

    assert row.deleted is False
    assert len(session.items) == 1

    await manager.dispatch(action_event(session, "delete", user_id=7))

    assert row.deleted is True
    assert session.closed is True
    assert context.channel.sent[-1] == "`Anime 1` removido da lista!"


@pytest.mark.asyncio
async def test_anime_list_payload_is_json_safe_and_progressive(monkeypatch):
    monkeypatch.setattr(animes_module, "anime_embed", simple_embed)
    rows = [FakeRow(mal_id=1, user_id="7"), FakeRow(mal_id=2, user_id="7", dubbed=True)]
    monkeypatch.setattr(animes_module.AnimesList, "get_user", lambda user_id: rows)
    context = make_context(FakeJikan())
    manager = make_manager(animes_module.AnimeListPagination, animes_module.ANIME_LIST)
    session = await manager.start(
        animes_module.ANIME_LIST,
        start_event(context),
        payload={"target_user_id": 7},
    )

    assert context.replied[0].content == "Buscando animes..."
    assert context.replied[0].view is not None

    await session.wait_for_loading()

    assert json.loads(json.dumps(session.to_payload())) == {
        "index": 0,
        "target_user_id": 7,
    }
    assert len(session.items) == 2
    assert context.replied[0].edits[-1][1].footer.text == "Animes: 1/2"
