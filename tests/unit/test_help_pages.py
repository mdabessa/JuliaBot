"""Layout, budget, and navigation tests for the paginated help listing."""

from types import SimpleNamespace

import pytest
from discord import Embed
from discord.ext import commands

from juliabot.cogs import help as help_module
from juliabot.sessions import (
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)


class FakeBot:
    """Minimal bot exposing the surface the help builder touches."""

    def __init__(self) -> None:
        self.cogs: dict[str, commands.Cog] = {}
        self.color = 0xE6DC56
        self.sessions = SessionManager(Registry())

    async def can_run(self, _ctx) -> bool:
        return True

    async def get_prefix(self, _message) -> str:
        return "!"


_UNSET = object()


class FakeSentMessage:
    def __init__(self, **kwargs) -> None:
        self.embed = kwargs.get("embed")
        self.content = kwargs.get("content")
        self.view = kwargs.get("view")
        self.edits: list[dict[str, object]] = []

    async def edit(self, content=_UNSET, embed=_UNSET, view=_UNSET):
        """Mirror discord.py's MISSING semantics for omitted arguments."""
        if content is not _UNSET:
            self.content = content
        if embed is not _UNSET:
            self.embed = embed
        if view is not _UNSET:
            self.view = view
        self.edits.append({"content": content, "embed": embed, "view": view})


class FakeContext:
    def __init__(self, bot: FakeBot, prefix: str = "!") -> None:
        self.bot = bot
        self.prefix = prefix
        self.command = None
        self.author = SimpleNamespace(id=7)
        self.guild = SimpleNamespace(id=10)
        self.channel = SimpleNamespace(id=20)
        self.message = SimpleNamespace(id=55)
        self.replies: list[FakeSentMessage] = []

    async def reply(self, content=None, embed=None, view=None):
        message = FakeSentMessage(content=content, embed=embed, view=view)
        self.replies.append(message)
        return message


def make_cog(
    name: str,
    command_names: list[str],
    *,
    title: str | None = None,
    aliases: list[str] | None = None,
    allowed: bool = True,
) -> commands.Cog:
    """Build a cog with the requested commands, bound like ``Bot.add_cog``."""
    attrs: dict[str, object] = {}
    for command_name in command_names:

        async def callback(_self, _ctx):
            return None

        attrs[command_name] = commands.command(
            name=command_name, aliases=list(aliases or ())
        )(callback)

    if title is not None:
        attrs["embed_title"] = title

    async def cog_check(_self, _ctx):
        return allowed

    if not allowed:
        attrs["cog_check"] = cog_check

    cog = type(f"{name.title()}Cog", (commands.Cog,), attrs)()
    # can_run resolves the owning cog's cog_check through Command.cog, which
    # Bot.add_cog assigns at registration time.
    for command in cog.get_commands():
        command.cog = cog
    return cog


def make_context(cogs: dict[str, commands.Cog]) -> FakeContext:
    bot = FakeBot()
    bot.cogs.update(cogs)
    return FakeContext(bot)


def event(context: FakeContext, key: str = "55") -> InteractionEvent:
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=key,
        user_id=context.author.id,
        guild_id=context.guild.id,
        channel_id=context.channel.id,
        message_id=context.message.id,
        raw=context,
    )


def registration() -> Registration:
    return Registration(
        name=help_module.HELP_PAGES,
        session_class=help_module.HelpPagination,
        trigger=TriggerType.COMPONENT,
        scope=Scope.CHANNEL,
        timeout=120,
        max_per_scope=1,
        resumable=False,
    )


def register(context: FakeContext) -> None:
    context.bot.sessions.registry.register(registration())


def render(page: help_module.HelpPage, index: int = 0, total: int = 1) -> Embed:
    """Render one page exactly like ``HelpPagination.render_item`` does."""
    embed = Embed(title=page.title, description=page.description, color=0)
    for name, value in page.fields:
        embed.add_field(name=name, value=value, inline=True)
    embed.set_footer(text=f"Página {index + 1}/{total}")
    return embed


@pytest.mark.asyncio
async def test_pages_hold_three_cogs_and_pad_partial_rows():
    context = make_context(
        {
            "animes": make_cog(
                "animes",
                ["search_anime", "anime_list"],
                title=":japanese_goblin:Animes.",
                aliases=["al"],
            ),
            "core": make_cog("core", ["ping"]),
            "fun": make_cog("fun", ["dice"]),
            "help": make_cog("help", ["help"]),
        }
    )

    pages = await help_module.build_help_pages(context)

    assert [page.cogs for page in pages] == [
        ("animes", "core", "fun"),
        ("help",),
    ]
    assert all(len(page.fields) % 3 == 0 for page in pages)
    assert pages[1].fields[1:] == (
        help_module.PADDING_FIELD,
        help_module.PADDING_FIELD,
    )


@pytest.mark.asyncio
async def test_page_renders_aliases_and_a_page_footer():
    context = make_context(
        {
            "animes": make_cog(
                "animes",
                ["search_anime", "anime_list"],
                title=":japanese_goblin:Animes.",
                aliases=["al"],
            ),
        }
    )

    pages = await help_module.build_help_pages(context)
    embed = render(pages[0], 0, 1)

    assert embed.title == help_module.PAGE_TITLE
    assert embed.footer.text == "Página 1/1"
    assert embed.fields[0].name == ":japanese_goblin:Animes."
    assert embed.fields[0].value == (
        "`search_anime` (al) `anime_list` (al)"
    )
    assert embed.fields[0].inline is True


@pytest.mark.asyncio
async def test_commands_without_aliases_render_bare():
    context = make_context({"core": make_cog("core", ["ping", "prefix"])})

    pages = await help_module.build_help_pages(context)

    assert pages[0].fields[0][1] == "`ping` `prefix`"


@pytest.mark.asyncio
async def test_pages_stay_inside_every_embed_budget():
    cogs: dict[str, commands.Cog] = {
        "bulk": make_cog(
            "bulk",
            [f"bulk_{index:02d}" for index in range(30)],
            aliases=["b1", "b2", "b3"],
        )
    }
    for index in range(25):
        cogs[f"cog{index:02d}"] = make_cog(
            f"cog{index:02d}", [f"cog{index:02d}_cmd"], aliases=["cc"]
        )

    context = make_context(cogs)
    pages = await help_module.build_help_pages(context)

    assert len(context.bot.cogs) == 26
    assert len(pages) == 9
    for index, page in enumerate(pages):
        embed = render(page, index, len(pages))
        assert len(page.fields) <= help_module.MAX_FIELDS_PER_PAGE
        for _, value in page.fields:
            assert len(value) <= help_module.MAX_FIELD_VALUE
        assert len(embed) <= help_module.MAX_EMBED_LENGTH
        # Only the final padded row may be `** **` filler.
        assert sum(1 for name, _ in page.fields if name != "** **") <= 3


@pytest.mark.asyncio
async def test_oversized_cogs_split_into_continuation_fields():
    big = [f"command_{index:02d}" for index in range(50)]
    context = make_context(
        {
            "alpha": make_cog("alpha", big, aliases=["aa0", "bb0", "cc0"]),
            "beta": make_cog("beta", big, aliases=["aa1", "bb1", "cc1"]),
        }
    )

    pages = await help_module.build_help_pages(context)

    names = [
        name
        for page in pages
        for name, _ in page.fields
        if name != help_module.PADDING_FIELD[0]
    ]
    assert names == [
        "alpha (1/2)",
        "alpha (2/2)",
        "beta (1/2)",
        "beta (2/2)",
    ]
    for page in pages:
        for _, value in page.fields:
            assert len(value) <= help_module.MAX_FIELD_VALUE
        assert len(render(page)) <= help_module.MAX_EMBED_LENGTH

    listing = " ".join(value for page in pages for _, value in page.fields)
    assert listing.count("`command_") == 100, "no command may be dropped"


@pytest.mark.asyncio
async def test_commands_blocked_by_cog_check_are_absent():
    context = make_context(
        {
            "debug": make_cog("debug", ["reload", "sessions"], allowed=False),
            "core": make_cog("core", ["ping"]),
        }
    )

    pages = await help_module.build_help_pages(context)

    assert [page.cogs for page in pages] == [("core",)]
    assert "reload" not in " ".join(value for _, value in pages[0].fields)


@pytest.mark.asyncio
async def test_cog_jump_starts_on_the_page_holding_that_cog():
    context = make_context(
        {
            name: make_cog(name, [f"{name}_cmd"])
            for name in ("alpha", "beta", "gamma", "delta")
        }
    )
    register(context)

    session = await context.bot.sessions.start(
        help_module.HELP_PAGES,
        event(context),
        payload={"index": 0, "cog": "delta"},
    )

    assert session.index == 1
    assert context.replies[-1].embed.footer.text == "Página 2/2"


@pytest.mark.asyncio
async def test_start_without_a_cog_opens_the_first_page():
    context = make_context({"core": make_cog("core", ["ping"])})
    register(context)

    session = await context.bot.sessions.start(
        help_module.HELP_PAGES, event(context), payload={"index": 0}
    )

    assert session.index == 0
    assert context.replies[-1].view is not None
    assert context.replies[-1].embed.footer.text == "Página 1/1"


@pytest.mark.asyncio
async def test_reinvocation_closes_the_previous_message_view():
    context = make_context({"core": make_cog("core", ["ping"])})
    register(context)

    first = await context.bot.sessions.start(
        help_module.HELP_PAGES, event(context, key="1"), payload={"index": 0}
    )
    assert context.replies[0].view is not None

    await context.bot.sessions.start(
        help_module.HELP_PAGES, event(context, key="2"), payload={"index": 0}
    )

    assert first.closed is True
    assert context.replies[0].view is None
    assert context.replies[0].embed is not None


@pytest.mark.asyncio
async def test_help_registration_is_channel_scoped_and_not_resumable():
    context = make_context({"core": make_cog("core", ["ping"])})
    cog = help_module.HelpCog(context.bot)

    registered = context.bot.sessions.registry.get(help_module.HELP_PAGES)

    assert cog.bot is context.bot
    assert registered.scope is Scope.CHANNEL
    assert registered.resumable is False
    assert registered.timeout == 120
    assert registered.max_per_scope == 1
