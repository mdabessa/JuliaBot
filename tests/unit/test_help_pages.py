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
    section: str | None = None,
    hidden: tuple[str, ...] = (),
) -> commands.Cog:
    """Build a cog with the requested commands, bound like ``Bot.add_cog``."""
    attrs: dict[str, object] = {}
    for command_name in command_names:

        async def callback(_self, _ctx):
            return None

        attrs[command_name] = commands.command(
            name=command_name,
            aliases=list(aliases or ()),
            hidden=command_name in hidden,
        )(callback)

    if title is not None:
        attrs["embed_title"] = title

    if section is not None:
        attrs["help_section"] = section

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
    if page.kind != help_module.PAGE_KIND_INDEX:
        embed.set_footer(text=f"Página {index + 1}/{total}")
    return embed


@pytest.mark.asyncio
async def test_cog_page_renders_aliases_and_a_page_footer():
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

    pages = await help_module.build_cog_pages(context, "!", "animes")
    embed = render(pages[0], 0, 1)

    assert embed.title == ":japanese_goblin:Animes."
    assert embed.footer.text == "Página 1/1"
    assert embed.fields[0].name == ":japanese_goblin:Animes."
    assert embed.fields[0].value == ("`search_anime` (al) `anime_list` (al)")
    assert embed.fields[0].inline is True


@pytest.mark.asyncio
async def test_commands_without_aliases_render_bare():
    context = make_context({"core": make_cog("core", ["ping", "prefix"])})

    pages = await help_module.build_cog_pages(context, "!", "core")

    assert pages[0].fields[0][1] == "`ping` `prefix`"


@pytest.mark.asyncio
async def test_cog_page_stays_inside_every_embed_budget():
    context = make_context(
        {
            "bulk": make_cog(
                "bulk",
                [f"bulk_{index:02d}" for index in range(30)],
                title=":package:Bulk.",
                aliases=["b1", "b2", "b3"],
            )
        }
    )

    pages = await help_module.build_cog_pages(context, "!", "bulk")

    assert len(pages) == 1
    page = pages[0]
    assert len(page.fields) <= help_module.MAX_FIELDS_PER_PAGE
    for _, value in page.fields:
        assert len(value) <= help_module.MAX_FIELD_VALUE
    assert len(render(page)) <= help_module.MAX_EMBED_LENGTH


@pytest.mark.asyncio
async def test_oversized_cogs_split_into_continuation_fields():
    big = [f"command_{index:02d}" for index in range(50)]
    context = make_context(
        {
            "alpha": make_cog("alpha", big, aliases=["aa0", "bb0", "cc0"]),
            "beta": make_cog("beta", big, aliases=["aa1", "bb1", "cc1"]),
        }
    )

    alpha = await help_module.build_cog_pages(context, "!", "alpha")
    beta = await help_module.build_cog_pages(context, "!", "beta")

    assert [name for page in alpha for name, _ in page.fields] == [
        "alpha (1/2)",
        "alpha (2/2)",
    ]
    assert [name for page in beta for name, _ in page.fields] == [
        "beta (1/2)",
        "beta (2/2)",
    ]
    for page in (*alpha, *beta):
        for _, value in page.fields:
            assert len(value) <= help_module.MAX_FIELD_VALUE
        assert len(render(page)) <= help_module.MAX_EMBED_LENGTH

    listing = " ".join(value for page in (*alpha, *beta) for _, value in page.fields)
    assert listing.count("`command_") == 100, "no command may be dropped"


@pytest.mark.asyncio
async def test_commands_blocked_by_cog_check_have_no_page():
    context = make_context(
        {
            "debug": make_cog("debug", ["reload", "sessions"], allowed=False),
            "core": make_cog("core", ["ping"]),
        }
    )

    assert await help_module.build_cog_pages(context, "!", "debug") == []
    assert await help_module.build_cog_pages(context, "!", "core") != []


@pytest.mark.asyncio
async def test_a_cog_payload_opens_that_cog_page():
    context = make_context(
        {
            name: make_cog(name, [f"{name}_cmd"], title=f"{name}.")
            for name in ("alpha", "beta", "gamma", "delta")
        }
    )
    register(context)

    session = await context.bot.sessions.start(
        help_module.HELP_PAGES,
        event(context),
        payload={"index": 0, "cog": "delta"},
    )

    embed = context.replies[-1].embed
    assert session.index == 0
    assert session.requested_cog == "delta"
    assert embed.title == "delta."
    assert embed.footer.text == "Página 1/1"
    assert embed.fields[0].name == "delta."
    assert embed.fields[0].value == "`delta_cmd`"


@pytest.mark.asyncio
async def test_start_without_a_cog_opens_the_index():
    context = make_context({"core": make_cog("core", ["ping"], title=":brain:Core.")})
    register(context)

    session = await context.bot.sessions.start(
        help_module.HELP_PAGES, event(context), payload={"index": 0}
    )

    embed = context.replies[-1].embed
    assert session.index == 0
    assert session.requested_cog == ""
    assert embed.title == help_module.PAGE_TITLE
    assert ":brain:Core. — 1 comando · `!help core`" in embed.description
    assert embed.fields == []
    # The index is a menu, not a numbered listing.
    assert embed.footer.text is None
    assert context.replies[-1].view is not None


@pytest.mark.asyncio
async def test_show_index_returns_to_the_index_in_place():
    context = make_context(
        {
            "alpha": make_cog("alpha", ["alpha_cmd"], title="alpha."),
            "beta": make_cog("beta", ["beta_cmd"], title="beta."),
        }
    )
    register(context)

    session = await context.bot.sessions.start(
        help_module.HELP_PAGES,
        event(context),
        payload={"index": 0, "cog": "alpha"},
    )
    assert session.requested_cog == "alpha"

    await session.show_index(event(context))

    assert session.closed is False
    assert session.requested_cog == ""
    assert session.index == 0
    embed = context.replies[-1].embed
    assert embed.title == help_module.PAGE_TITLE
    assert "beta." in embed.description
    assert embed.footer.text is None


def test_session_exposes_a_categorias_action():
    context = make_context({"core": make_cog("core", ["ping"])})
    registered = registration()
    session = registered.session_class(registered, event(context))

    assert [action.label for action in session.actions] == [
        "Anterior",
        "Próximo",
        "Categorias",
    ]


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


@pytest.mark.asyncio
async def test_index_lists_each_cog_with_a_count_and_an_invocation():
    context = make_context(
        {
            "animes": make_cog(
                "animes",
                ["search_anime", "anime_list"],
                title=":japanese_goblin:Animes.",
            ),
            "core": make_cog("core", ["ping"]),
        }
    )

    pages = await help_module.build_help_index(context)

    assert len(pages) == 1
    page = pages[0]
    assert page.kind == help_module.PAGE_KIND_INDEX
    assert page.title == help_module.PAGE_TITLE
    assert page.fields == ()

    lines = page.description.splitlines()
    assert lines[0] == f"**{help_module.MAIN_SECTION_TITLE}**"
    assert ":japanese_goblin:Animes. — 2 comandos · `!help animes`" in lines
    # A cog without an embed_title falls back to its registered name, and a
    # single command keeps the singular form.
    assert "core — 1 comando · `!help core`" in lines
    assert lines[-1] == "`!help comando` para detalhes · `!help categoria` para abrir."
    assert page.cogs == ("animes", "core")


@pytest.mark.asyncio
async def test_index_omits_cogs_the_invoker_cannot_use():
    context = make_context(
        {
            "debug": make_cog("debug", ["reload", "sessions"], allowed=False),
            "core": make_cog("core", ["ping"], title=":brain:Core."),
        }
    )

    pages = await help_module.build_help_index(context)

    assert ":brain:Core." in pages[0].description
    assert "debug" not in pages[0].description
    assert pages[0].cogs == ("core",)


@pytest.mark.asyncio
async def test_index_puts_sectioned_cogs_after_the_main_block():
    context = make_context(
        {
            "animes": make_cog("animes", ["search_anime"], title="Animes."),
            "mal": make_cog(
                "mal",
                ["characters", "top"],
                title=":mag:MyAnimeList.",
                section="API do MyAnimeList",
            ),
        }
    )

    description = (await help_module.build_help_index(context))[0].description
    main_block, api_block = description.split("**API do MyAnimeList**")

    assert description.index("**Comandos**") < description.index(
        "**API do MyAnimeList**"
    )
    assert "Animes." in main_block
    assert ":mag:MyAnimeList." in api_block


@pytest.mark.asyncio
async def test_index_stays_one_embed_for_many_cogs():
    context = make_context(
        {
            f"cog{index:02d}": make_cog(f"cog{index:02d}", [f"cog{index:02d}_cmd"])
            for index in range(26)
        }
    )

    pages = await help_module.build_help_index(context)

    assert len(pages) == 1
    assert len(pages[0].description) <= help_module.MAX_DESCRIPTION


@pytest.mark.asyncio
async def test_index_spills_into_numbered_pages_past_the_description_limit(
    monkeypatch,
):
    monkeypatch.setattr(help_module, "MAX_DESCRIPTION", 160)
    context = make_context(
        {
            f"cog{index:02d}": make_cog(f"cog{index:02d}", [f"cog{index:02d}_cmd"])
            for index in range(6)
        }
    )

    pages = await help_module.build_help_index(context)

    assert len(pages) > 1
    assert pages[0].title == f"{help_module.PAGE_TITLE} (1/{len(pages)})"
    assert "para detalhes" not in pages[0].description
    assert "para detalhes" in pages[-1].description
    for page in pages:
        assert page.kind == help_module.PAGE_KIND_INDEX
        assert page.fields == ()
        assert page.description == page.description.strip("\n")


@pytest.mark.asyncio
async def test_cog_pages_ignore_the_three_cog_page_cap():
    bulk = [f"command_{index:03d}" for index in range(120)]
    context = make_context(
        {
            "alpha": make_cog(
                "alpha", bulk, title=":alpha:Alpha.", aliases=["a0", "b0", "c0"]
            )
        }
    )

    pages = await help_module.build_cog_pages(context, "!", "alpha")

    assert len(pages) == 1
    page = pages[0]
    assert page.kind == help_module.PAGE_KIND_COMMANDS
    assert page.title == ":alpha:Alpha."
    assert page.cogs == ("alpha",)
    assert page.description == "!help comando para detalhes"
    # 120 commands no longer fit one 1024-char value: the cog spills into
    # continuation fields on the same page instead of being capped.
    assert len(page.fields) >= 4
    assert len(page.fields) <= help_module.MAX_FIELDS_PER_PAGE
    listing = " ".join(value for _, value in page.fields)
    assert listing.count("`command_") == 120
    assert all(len(value) <= help_module.MAX_FIELD_VALUE for _, value in page.fields)


@pytest.mark.asyncio
async def test_cog_pages_skip_hidden_commands():
    context = make_context(
        {
            "core": make_cog(
                "core", ["ping", "secret"], title=":brain:Core.", hidden=("secret",)
            )
        }
    )

    pages = await help_module.build_cog_pages(context, "!", "core")

    assert len(pages) == 1
    assert "`ping`" in pages[0].fields[0][1]
    assert "secret" not in pages[0].fields[0][1]


@pytest.mark.asyncio
async def test_cog_pages_for_an_unknown_or_empty_cog_are_empty():
    context = make_context({"core": make_cog("core", ["ping"])})

    assert await help_module.build_cog_pages(context, "!", "nope") == []
    assert await help_module.build_cog_pages(context, "!", "") == []
