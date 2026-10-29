import logging

import pytest
from discord import Intents
from discord.ext import commands

from juliabot import jikan_catalog as catalog
from juliabot import jikan_commands as generator
from juliabot.cogs import anime_api as anime_api_module


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


class FakeContext:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, content=None, **kwargs):
        self.sent.append({"content": content, **kwargs})

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


def test_build_commands_skips_curated_routes():
    specs = catalog.load_specs()

    built = generator.build_commands(FakeCog(), specs)

    assert "search_anime" not in {command.name for command in built}
    assert len(built) == sum(1 for spec in specs if not spec.curated)


def test_build_commands_respects_the_allowlist():
    built = generator.build_commands(
        FakeCog(), catalog.load_specs(), allowlist={"get_anime_themes"}
    )

    assert [command.name for command in built] == ["anime_themes"]


def test_build_commands_skips_names_taken_by_other_commands(caplog):
    existing = commands.Command(_noop, name="anime_themes")
    bot = FakeBot(existing)

    with caplog.at_level(logging.WARNING):
        built = generator.build_commands(
            FakeCog(bot=bot), catalog.load_specs(), allowlist={"get_anime_themes"}
        )

    assert built == ()
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
