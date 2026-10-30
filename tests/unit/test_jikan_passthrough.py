"""Tests for the ``!jikan`` passthrough command."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from discord import Intents
from discord.ext import commands

from juliabot import jikan_catalog as catalog
from juliabot import jikan_errors, jikan_sessions
from juliabot.cogs import jikan as jikan_module


class FakeClient:
    def __init__(self, payload=None):
        self.payload = (
            payload if payload is not None else {"data": {"openings": ["OP1"]}}
        )
        self.calls: list[tuple[str, dict]] = []

    async def get_anime_themes(self, **kwargs):
        self.calls.append(("get_anime_themes", kwargs))
        return self.payload

    async def get_anime_ids(self, **kwargs):
        self.calls.append(("get_anime_ids", kwargs))
        return {"data": [1, 2, 3]}

    async def get_top_anime(self, **kwargs):
        self.calls.append(("get_top_anime", kwargs))
        return SimpleNamespace(
            data=[{"mal_id": 1, "title": "Frieren"}],
            pagination=SimpleNamespace(has_next_page=True, current_page=1),
        )


class FakeContext:
    def __init__(self, owner=False, bot=None):
        self.sent: list[dict] = []
        self.bot = bot
        self.author = SimpleNamespace(id=42)
        self.guild = SimpleNamespace(id=10)
        self.channel = SimpleNamespace(id=20)
        self.message = SimpleNamespace(id=30)
        self.command = None
        self._owner = owner

    async def send(self, content=None, **kwargs):
        self.sent.append({"content": content, **kwargs})
        return SimpleNamespace(edit=self._noop)

    async def reply(self, content=None, embed=None, view=None):
        self.sent.append({"content": content, "embeds": [embed], "view": view})
        return SimpleNamespace(edit=self._noop)

    async def _noop(self, **_kwargs):
        return None

    @property
    def text(self) -> str:
        return "\n".join(str(message["content"]) for message in self.sent)


def make_bot(client, owner=False):
    bot = commands.Bot(command_prefix="!", intents=Intents.default())
    bot.jikan = client
    bot.is_owner = lambda _author: _truthy(owner)
    return bot


def _truthy(value):
    async def value_of(_author):
        return value

    return value_of(None)


def make_cog(client, owner=False):
    bot = make_bot(client, owner)
    bot.jikan = client
    return bot, jikan_module.JikanCog(bot)


def run(cog, ctx, argument):
    import asyncio

    return asyncio.run(
        jikan_module.JikanCog.jikan_command.callback(cog, ctx, argument=argument)
    )


def test_command_metadata():
    bot, cog = make_cog(FakeClient())
    command = jikan_module.JikanCog.jikan_command

    assert command.name == "jikan"
    assert command.aliases == ["api"]
    assert command.brief
    assert "chave=valor" in command.usage
    assert command.cooldown is not None


def test_without_arguments_shows_the_usage():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "")

    assert "--list" in ctx.text
    assert "--schema" in ctx.text
    assert "!help !anime_api" in ctx.text


def test_calls_a_route_with_parsed_arguments():
    client = FakeClient()
    bot, cog = make_cog(client)
    ctx = FakeContext()

    run(cog, ctx, "get_anime_themes 1")

    assert client.calls == [("get_anime_themes", {"anime_id": 1})]
    assert ctx.sent[0]["embeds"][0].fields[0].value == "OP1"


def test_accepts_the_command_name_without_the_get_prefix():
    client = FakeClient()
    bot, cog = make_cog(client)
    ctx = FakeContext()

    run(cog, ctx, "anime_themes 1")

    assert client.calls == [("get_anime_themes", {"anime_id": 1})]


def test_unknown_route_suggests_similar_names():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "get_anime_theme")

    assert "Rota desconhecida" in ctx.text
    assert "get_anime_themes" in ctx.text


def test_argument_errors_come_from_the_parser():
    client = FakeClient()
    bot, cog = make_cog(client)
    ctx = FakeContext()

    run(cog, ctx, "get_anime_themes abc")

    assert client.calls == []
    assert "precisa ser um número inteiro" in ctx.text


def test_hidden_routes_are_blocked_for_everyone_but_the_owner():
    client = FakeClient()
    bot, cog = make_cog(client)
    ctx = FakeContext(owner=False)

    run(cog, ctx, "get_anime_ids")

    assert client.calls == []
    assert "Rota desconhecida" in ctx.text


def test_the_owner_can_reach_a_hidden_route():
    client = FakeClient()
    bot, cog = make_cog(client, owner=True)
    ctx = FakeContext(owner=True)

    run(cog, ctx, "get_anime_ids")

    assert client.calls == [("get_anime_ids", {})]
    assert ctx.sent[0]["content"] is not None


def test_list_shows_every_visible_route():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "--list")

    listed = " ".join(embed.description for embed in ctx.sent[0]["embeds"])
    for spec in catalog.load_specs():
        if spec.hidden:
            assert f"`{spec.name}`" not in listed, spec.name
        else:
            assert f"`{spec.name}`" in listed, spec.name


def test_list_filters_by_group():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "--list manga")

    embeds = ctx.sent[0]["embeds"]
    assert len(embeds) == 1
    assert embeds[0].title == ":books:Manga"
    assert "`manga_news`" in embeds[0].description
    assert "`top_anime`" not in embeds[0].description


def test_list_rejects_an_unknown_group():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "--list animes")

    assert "Grupo desconhecido" in ctx.text
    assert "anime" in ctx.text


def test_list_accepts_the_short_flag():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "-l anime")

    assert ctx.sent[0]["embeds"][0].title.startswith(":japanese_goblin:Anime")


def test_a_hidden_route_is_absent_from_the_listing_for_others():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext(owner=False)

    run(cog, ctx, "--list")

    listed = " ".join(embed.description for embed in ctx.sent[0]["embeds"])
    assert "`anime_denied`" not in listed


def test_the_owner_sees_hidden_routes_in_the_listing():
    bot, cog = make_cog(FakeClient(), owner=True)
    ctx = FakeContext(owner=True)

    run(cog, ctx, "--list")

    listed = " ".join(embed.description for embed in ctx.sent[0]["embeds"])
    assert "`anime_denied`" in listed


def test_schema_describes_the_parameters():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "--schema get_anime_stacks")

    embed = ctx.sent[0]["embed"]
    fields = {field.name: field.value for field in embed.fields}
    assert "anime_id" in fields
    assert "obrigatório" in fields["anime_id"]
    assert "opcional" in fields["sfw"]
    assert "paginado" not in embed.description
    assert embed.footer.text.startswith("anime_stacks <anime_id>")


def test_schema_reports_the_response_shape():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "--schema get_anime_themes")

    fields = {field.name: field.value for field in ctx.sent[0]["embed"].fields}
    assert fields["Retorno"] == "`object`"
    assert fields["Rota"] == "`get_anime_themes`"
    assert fields["Chamada"] == "`await client.get_anime_themes(anime_id=...)`"


def test_schema_without_a_route_shows_the_usage():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "--schema")

    assert "--list" in ctx.text


def test_schema_of_an_unknown_route_suggests_names():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "--schema get_top_anim")

    assert "Rota desconhecida" in ctx.text
    assert "get_top_anime" in ctx.text


def test_schema_of_a_hidden_route_is_refused_for_others():
    bot, cog = make_cog(FakeClient())
    ctx = FakeContext()

    run(cog, ctx, "--schema get_anime_ids")

    assert "Rota desconhecida" in ctx.text
    assert "get_anime_ids" not in ctx.text.replace(
        "Rota desconhecida: `get_anime_ids`.", ""
    )


def test_a_paginated_route_goes_through_the_session():
    client = FakeClient()
    bot, cog = make_cog(client)
    ctx = FakeContext(bot=bot)

    run(cog, ctx, "get_top_anime type=tv")

    session = bot.sessions.active()[0]
    assert session.registration.name == jikan_sessions.JIKAN_PAGE
    assert session.to_payload()["route"] == "get_top_anime"
    assert ctx.sent[0]["embeds"][0].title == "Frieren"


def test_a_session_without_a_client_reports_it_instead_of_rendering_nothing():
    client = FakeClient()
    bot, cog = make_cog(client)
    ctx = FakeContext()  # no bot: the session cannot resolve the client

    run(cog, ctx, "get_top_anime")

    assert "não está disponível" in ctx.text


def test_api_failures_are_reported():
    class FailingClient:
        async def get_anime_themes(self, **_kwargs):
            raise jikan_errors.JikanCallError(
                "A API do MyAnimeList está instável agora."
            )

    bot, cog = make_cog(FailingClient())
    ctx = FakeContext()

    run(cog, ctx, "get_anime_themes 1")

    assert "instável" in ctx.text


def test_the_cog_shares_the_bot_client_and_registers_the_session():
    client = FakeClient()
    bot = make_bot(client)
    cog = jikan_module.JikanCog(bot)

    assert cog.jikan is client
    assert bot.jikan is client
    assert bot.sessions.registry.get(jikan_sessions.JIKAN_PAGE) is not None


@pytest.mark.asyncio
async def test_the_cog_registers_on_a_bot_without_collisions():
    bot = make_bot(FakeClient())
    cog = jikan_module.JikanCog(bot)

    await bot.add_cog(cog)

    try:
        command = bot.get_command("jikan")
        assert command is not None
        assert command.cog is cog
        assert bot.get_command("api") is command
    finally:
        await bot.remove_cog("jikan")
        await bot.close()
