import asyncio
import logging
from types import SimpleNamespace

import aiohttp
import pytest
from discord import Intents
from discord.ext import commands

from juliabot import jikan_catalog as catalog
from juliabot import jikan_commands as generator
from juliabot import jikan_errors, jikan_sessions
from juliabot.cogs import anime_api as anime_api_module
from juliabot.cogs import help as help_module
from juliabot.cogs import mal as mal_module
from juliabot.cogs import manga as manga_module


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def model_dump(self):
        return self._data


class FakeClient:
    def __init__(self, data=None):
        self.calls: list[tuple[str, dict]] = []
        self._data = {"data": {"openings": ["Theme"]}} if data is None else data

    async def get_anime_themes(self, **kwargs):
        self.calls.append(("get_anime_themes", kwargs))
        return FakeResponse(self._data)


class FailingClient:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    async def get_anime_themes(self, **_kwargs):
        self.calls += 1
        raise self.error


class FakeContext:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, content=None, **kwargs):
        self.sent.append({"content": content, **kwargs})

    async def reply(self, content=None, embed=None, view=None):
        self.sent.append({"content": content, "embeds": [embed], "view": view})
        return SimpleNamespace(edit=self._edit)

    async def _edit(self, **_kwargs):
        return None

    @property
    def contents(self) -> list[str]:
        return [message["content"] for message in self.sent if message["content"]]


class FakeCog:
    def __init__(self, bot=None, jikan=None):
        self.bot = bot
        self.jikan = jikan


class FakeBot:
    """Minimal bot exposing ``get_command`` for the collision guard."""

    def __init__(self, *existing):
        self.existing = {command.name: command for command in existing}
        self.jikan = None

    def get_command(self, name):
        return self.existing.get(name)


async def _noop(ctx):
    return None


@pytest.fixture(scope="module")
def themes() -> catalog.RouteSpec:
    return next(
        spec for spec in catalog.load_specs() if spec.route == "get_anime_themes"
    )


def test_command_carries_the_help_metadata(themes):
    command = generator.build_command(FakeCog(), themes)

    assert command.name == themes.name
    assert command.brief == themes.brief
    assert command.description == themes.description
    assert command.usage == "anime_themes <anime_id>"
    assert command.aliases == list(themes.aliases)
    assert command.hidden is False
    assert command.extras["route"] == "get_anime_themes"
    # Only the rest parameter survives inspection; the cog and the context are
    # injected by discord.py.
    assert list(command.params) == ["raw"]


def test_command_carries_the_catalog_cooldown(themes):
    command = generator.build_command(FakeCog(), themes)

    assert command.cooldown is not None
    assert (command.cooldown.rate, command.cooldown.per) == themes.cooldown


def test_hidden_routes_are_marked_hidden():
    hidden_spec = next(
        spec for spec in catalog.load_specs() if spec.route == "get_anime_deleted"
    )

    command = generator.build_command(FakeCog(), hidden_spec)

    assert command.hidden is True


@pytest.mark.asyncio
async def test_dispatch_calls_the_route_with_parsed_arguments(themes):
    client = FakeClient()
    cog = FakeCog(jikan=client)
    command = generator.build_command(cog, themes)
    ctx = FakeContext()

    await command.callback(cog, ctx, raw="1")

    assert client.calls == [("get_anime_themes", {"anime_id": 1})]
    assert ctx.sent[0]["embeds"][0].fields[0].value == "Theme"


@pytest.mark.asyncio
async def test_dispatch_prefers_the_client_shared_through_the_bot(themes):
    shared = FakeClient()
    bot = FakeBot()
    bot.jikan = shared
    cog = FakeCog(bot=bot, jikan=FakeClient())
    command = generator.build_command(cog, themes)

    await command.callback(cog, FakeContext(), raw="1")

    assert shared.calls == [("get_anime_themes", {"anime_id": 1})]


@pytest.mark.asyncio
async def test_argument_errors_are_answered_without_calling_the_api(themes):
    client = FakeClient()
    cog = FakeCog(jikan=client)
    command = generator.build_command(cog, themes)
    ctx = FakeContext()

    await command.callback(cog, ctx, raw="abc")

    assert client.calls == []
    assert "`anime_id` precisa ser um número inteiro" in ctx.contents[0]


@pytest.mark.asyncio
async def test_missing_client_is_reported(themes):
    cog = FakeCog()
    command = generator.build_command(cog, themes)
    ctx = FakeContext()

    await command.callback(cog, ctx, raw="1")

    assert "não está disponível" in ctx.contents[0]


@pytest.mark.asyncio
async def test_payloads_are_rendered_into_one_message(themes):
    client = FakeClient(data={"data": {"openings": ["OP1"], "endings": ["ED1"]}})
    cog = FakeCog(jikan=client)
    command = generator.build_command(cog, themes)
    ctx = FakeContext()

    await command.callback(cog, ctx, raw="1")

    assert len(ctx.sent) == 1
    fields = {field.name: field.value for field in ctx.sent[0]["embeds"][0].fields}
    assert fields == {"Openings": "OP1", "Endings": "ED1"}


@pytest.mark.asyncio
async def test_api_failures_are_answered_with_a_friendly_message(themes):
    client = FailingClient(
        aiohttp.ClientResponseError(
            request_info=None, history=(), status=404, message="nope"
        )
    )
    cog = FakeCog(jikan=client)
    command = generator.build_command(cog, themes)
    ctx = FakeContext()

    await command.callback(cog, ctx, raw="999999999")

    assert ctx.contents == ["Não encontrei nada com esse id ou critério."]
    assert ctx.sent[0].get("embeds") is None


@pytest.mark.asyncio
async def test_a_rate_limited_call_reports_the_wait_and_blocks_the_next_one(themes):
    client = FailingClient(
        aiohttp.ClientResponseError(
            request_info=None,
            history=(),
            status=429,
            message="slow down",
            headers={"Retry-After": "12"},
        )
    )
    cog = FakeCog(jikan=client)
    command = generator.build_command(cog, themes)
    ctx = FakeContext()

    try:
        await command.callback(cog, ctx, raw="1")
        assert "limitando as requisições" in ctx.contents[0]
        assert "12s" in ctx.contents[0]
        assert client.calls == 1

        await command.callback(cog, ctx, raw="1")
        assert client.calls == 1, "the second call must not reach the API"
        assert "limitando as requisições" in ctx.contents[1]
    finally:
        jikan_errors.GUARD.reset()


@pytest.mark.asyncio
async def test_successful_calls_are_not_affected_by_the_guard(themes):
    client = FakeClient()
    cog = FakeCog(jikan=client)
    command = generator.build_command(cog, themes)

    await command.callback(cog, FakeContext(), raw="1")

    assert client.calls == [("get_anime_themes", {"anime_id": 1})]


def test_command_has_a_per_user_cooldown(themes):
    command = generator.build_command(FakeCog(), themes)

    assert command.cooldown.rate == 1
    assert command.cooldown.per == themes.cooldown[1]


def test_build_commands_skips_curated_routes():
    specs = catalog.load_specs()

    built = generator.build_commands(FakeCog(), specs)

    assert "search_anime" not in {command.name for command in built}
    assert len(built) == sum(1 for spec in specs if not spec.curated)


def test_build_commands_skips_names_taken_by_other_commands(caplog):
    existing = commands.Command(_noop, name="anime_themes")
    bot = FakeBot(existing)

    with caplog.at_level(logging.WARNING):
        built = generator.build_commands(FakeCog(bot=bot), catalog.load_specs())

    names = {command.name for command in built}
    assert "anime_themes" not in names
    assert len(built) == sum(1 for spec in catalog.load_specs() if not spec.curated) - 1
    assert "already used by another command" in caplog.text


def test_build_commands_skips_duplicate_labels_inside_one_batch(caplog, themes):
    twin = next(spec for spec in catalog.load_specs() if spec.route == "get_anime_full")
    duplicated = catalog.RouteSpec(
        route=twin.route,
        name=themes.name,
        group=twin.group,
        brief=twin.brief,
        description=twin.description,
        params=twin.params,
    )

    with caplog.at_level(logging.WARNING):
        built = generator.build_commands(FakeCog(), [themes, duplicated])

    assert [command.name for command in built] == ["anime_themes"]
    assert "was already generated" in caplog.text


@pytest.mark.asyncio
async def test_send_rendered_sends_a_json_attachment(themes, monkeypatch):
    from juliabot.jikan_render import RenderResult

    attachment = object()
    ctx = FakeContext()

    await generator.send_rendered(ctx, RenderResult(content=None, file=attachment))

    assert ctx.sent == [{"content": None, "file": attachment}]


@pytest.mark.asyncio
async def test_cog_registers_generated_commands_on_a_real_bot():
    bot = commands.Bot(command_prefix="!", intents=Intents.default())
    bot.jikan = FakeClient()
    cog = anime_api_module.AnimeApiCog(bot)

    await bot.add_cog(cog)

    try:
        registered = bot.get_command("anime_themes")
        assert registered is not None
        assert registered.cog is cog
        assert registered.brief
        assert registered.usage == "anime_themes <anime_id>"
        assert "anime_themes" in {command.name for command in cog.walk_commands()}
    finally:
        await bot.remove_cog(cog.qualified_name)
        await bot.close()


@pytest.mark.asyncio
async def test_reloading_the_cog_does_not_duplicate_commands():
    bot = commands.Bot(command_prefix="!", intents=Intents.default())
    bot.jikan = FakeClient()

    try:
        await bot.add_cog(anime_api_module.AnimeApiCog(bot))
        await bot.remove_cog("anime_api")
        await bot.add_cog(anime_api_module.AnimeApiCog(bot))

        assert bot.get_command("anime_themes") is not None
        assert len([c for c in bot.commands if c.name == "anime_themes"]) == 1
    finally:
        await bot.remove_cog("anime_api")
        await bot.close()


@pytest.mark.asyncio
async def test_the_three_generated_cogs_expose_every_route(caplog):
    bot = commands.Bot(command_prefix="!", intents=Intents.default())
    bot.jikan = FakeClient()
    cogs = [
        anime_api_module.AnimeApiCog(bot),
        manga_module.MangaCog(bot),
        mal_module.MalCog(bot),
    ]

    with caplog.at_level(logging.WARNING):
        for cog in cogs:
            await bot.add_cog(cog)

    try:
        specs = [spec for spec in catalog.load_specs() if not spec.curated]
        missing = [spec.name for spec in specs if bot.get_command(spec.name) is None]
        assert missing == []
        assert "Skipping generated command" not in caplog.text

        counts = {
            cog.qualified_name: len(cog.get_commands()) for cog in bot.cogs.values()
        }
        assert counts == {"anime_api": 25, "manga": 18, "mal": 53}
    finally:
        for cog in cogs:
            await bot.remove_cog(cog.qualified_name)
        await bot.close()


@pytest.mark.asyncio
async def test_generated_cogs_share_one_client_and_one_session():
    bot = commands.Bot(command_prefix="!", intents=Intents.default())
    bot.jikan = FakeClient()
    shared = bot.jikan
    cogs = [
        anime_api_module.AnimeApiCog(bot),
        manga_module.MangaCog(bot),
        mal_module.MalCog(bot),
    ]

    try:
        assert bot.jikan is shared
        assert all(cog.jikan is shared for cog in cogs)
        assert bot.sessions.registry.get(jikan_sessions.JIKAN_PAGE) is not None
    finally:
        for cog in cogs:
            await bot.remove_cog(cog.qualified_name)
        await bot.close()


@pytest.mark.asyncio
async def test_hidden_routes_are_registered_but_not_listed():
    bot = commands.Bot(command_prefix="!", intents=Intents.default())
    bot.jikan = FakeClient()
    cog = mal_module.MalCog(bot)

    await bot.add_cog(cog)

    try:
        command = bot.get_command("character_ids")
        assert command is not None
        assert command.hidden is True
        assert command in list(cog.walk_commands())
    finally:
        await bot.remove_cog(cog.qualified_name)
        await bot.close()


@pytest.mark.asyncio
async def test_a_paginated_route_starts_a_session_instead_of_dumping_embeds():
    bot = commands.Bot(command_prefix="!", intents=Intents.default())

    class PagedClient:
        async def get_top_anime(self, **kwargs):
            return SimpleNamespace(
                data=[{"mal_id": 1, "title": "Frieren"}],
                pagination=SimpleNamespace(has_next_page=True, current_page=1),
            )

    bot.jikan = PagedClient()
    cog = mal_module.MalCog(bot)
    command = generator.build_command(cog, _spec("get_top_anime"))
    ctx = FakeContext()
    ctx.bot = bot
    ctx.author = SimpleNamespace(id=42)
    ctx.guild = SimpleNamespace(id=10)
    ctx.channel = SimpleNamespace(id=20, send=None)
    ctx.message = SimpleNamespace(id=99)

    await command.callback(cog, ctx, raw="type=tv")

    session = bot.sessions.active()[0]
    assert session.registration.name == jikan_sessions.JIKAN_PAGE
    assert session.to_payload()["route"] == "get_top_anime"
    assert session.to_payload()["kwargs"] == {"type": "tv"}
    assert len(ctx.sent) == 1
    assert ctx.sent[0]["embeds"][0].title == "Frieren"


@pytest.mark.asyncio
async def test_a_paginated_route_falls_back_to_static_rendering_without_a_manager():
    cog = FakeCog(jikan=PagedClientForFallback())
    command = generator.build_command(cog, _spec("get_top_anime"))
    ctx = FakeContext()

    await command.callback(cog, ctx, raw="")

    assert len(ctx.sent) == 1
    assert ctx.sent[0]["embeds"][0].description.startswith("• [Frieren]")


def _spec(route: str) -> catalog.RouteSpec:
    return next(spec for spec in catalog.load_specs() if spec.route == route)


@pytest.mark.asyncio
async def test_help_lists_every_visible_generated_command_within_budget():
    bot = commands.Bot(command_prefix="!", intents=Intents.default())
    bot.jikan = FakeClient()
    cogs = [
        anime_api_module.AnimeApiCog(bot),
        manga_module.MangaCog(bot),
        mal_module.MalCog(bot),
    ]
    for cog in cogs:
        await bot.add_cog(cog)

    class HelpContext:
        prefix = "!"
        author = SimpleNamespace(id=1)
        guild = SimpleNamespace(id=10)
        channel = SimpleNamespace(id=20)
        message = SimpleNamespace(id=30)
        command = None
        permissions = SimpleNamespace()

        def __init__(self) -> None:
            self.bot = bot

    try:
        pages = await help_module.build_help_pages(HelpContext(), "!")

        assert pages
        listed = " ".join(value for page in pages for _name, value in page.fields)
        for spec in catalog.load_specs():
            if spec.curated or spec.hidden:
                continue
            assert f"`{spec.name}`" in listed, spec.name

        for spec in catalog.load_specs():
            if not spec.hidden:
                continue
            assert f"`{spec.name}`" not in listed, spec.name

        for page in pages:
            assert sum(len(name) + len(value) for name, value in page.fields) <= 6000
            assert all(len(value) <= 1024 for _name, value in page.fields)

        titles = " ".join(name for page in pages for name, _value in page.fields)
        assert "Animes (API)." in titles
        assert ":books:Mangás." in titles
        assert ":mag:MyAnimeList." in titles
    finally:
        for cog in cogs:
            await bot.remove_cog(cog.qualified_name)
        await bot.close()


class PagedClientForFallback:
    async def get_top_anime(self, **_kwargs):
        return {
            "data": [{"mal_id": 1, "title": "Frieren", "url": "https://x/1"}],
            "pagination": {"has_next_page": True, "current_page": 1},
        }
