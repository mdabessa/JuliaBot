from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Awaitable, Callable

import pytest
import pytz
from discord import Embed
from discord.ext import commands

import juliabot.models as models
from juliabot.cogs import ai as ai_module
from juliabot.cogs import animes as animes_module
from juliabot.cogs import changelog as changelog_module
from juliabot.cogs import core as core_module
from juliabot.cogs import debug as debug_module
from juliabot.cogs import error_handler as error_handler_module
from juliabot.cogs import fun as fun_module
from juliabot.cogs import game as game_module
from juliabot.cogs import help as help_module
from juliabot.cogs import reminder as reminder_module
from juliabot.cogs import server_config as server_config_module
from juliabot.cogs import twitch as twitch_module
from juliabot.cogs import utilities as utilities_module

COG_MODULES = [
    ai_module,
    animes_module,
    changelog_module,
    core_module,
    debug_module,
    error_handler_module,
    fun_module,
    game_module,
    help_module,
    reminder_module,
    server_config_module,
    twitch_module,
    utilities_module,
]


@dataclass(frozen=True)
class CommandCase:
    cog: str
    command: str
    runner: Callable[[pytest.MonkeyPatch, Path], Awaitable[None]]

    @property
    def id(self) -> str:
        return f"{self.cog}::{self.command}"


class AsyncHistory:
    def __init__(self, messages):
        self._messages = list(messages)

    def __aiter__(self):
        self._iterator = iter(self._messages)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeSentMessage:
    def __init__(self, content=None, embed=None, file=None, channel=None):
        self.content = content
        self.embed = embed
        self.file = file
        self.channel = channel
        self.edits: list[dict[str, object]] = []
        self.deleted = False
        self.reactions: list[str] = []

    async def edit(self, content=None, embed=None):
        if content is not None:
            self.content = content
        if embed is not None:
            self.embed = embed
        self.edits.append({"content": content, "embed": embed})

    async def delete(self):
        self.deleted = True

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)


class FakeUser:
    def __init__(
        self, user_id: int, display_name: str | None = None, bot: bool = False
    ):
        self.id = user_id
        self.bot = bot
        self.display_name = display_name or f"user-{user_id}"
        self.mention = f"<@{user_id}>"

    def __str__(self) -> str:
        return self.display_name


class FakeGuild:
    def __init__(self, guild_id: int, name: str = "Guild"):
        self.id = guild_id
        self.name = name
        self._channels: dict[int, FakeChannel] = {}

    def add_channel(self, channel: "FakeChannel") -> None:
        self._channels[channel.id] = channel

    def get_channel(self, channel_id: int):
        return self._channels.get(channel_id)

    def __str__(self) -> str:
        return self.name


class FakeChannel:
    def __init__(
        self, channel_id: int, name: str = "general", guild: FakeGuild | None = None
    ):
        self.id = channel_id
        self.name = name
        self.guild = guild
        self.mention = f"<#${channel_id}>".replace("$", "")
        self.sent_messages: list[FakeSentMessage] = []
        self.history_messages: list[object] = []

    async def send(self, content=None, embed=None, file=None):
        message = FakeSentMessage(content=content, embed=embed, file=file, channel=self)
        self.sent_messages.append(message)
        return message

    def permissions_for(self, _user):
        return SimpleNamespace(administrator=True)

    def history(self, **_kwargs):
        return AsyncHistory(self.history_messages)

    def __str__(self) -> str:
        return self.name


class FakeMessage:
    def __init__(
        self,
        content: str,
        author: FakeUser,
        channel: FakeChannel,
        guild: FakeGuild | None,
        message_id: int = 1000,
        mentions: list[FakeUser] | None = None,
    ):
        self.content = content
        self.author = author
        self.channel = channel
        self.guild = guild
        self.id = message_id
        self.mentions = mentions or []
        self.reactions: list[str] = []

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)


class FakeBot:
    def __init__(self):
        self.color = 0xE6DC56
        self.user = FakeUser(9999, display_name="JuliaBot", bot=True)
        self.cogs: dict[str, commands.Cog] = {}
        self.extensions: dict[str, object] = {}
        self.reloaded_extensions: list[str] = []
        self.processed_messages: list[FakeMessage] = []
        self.channel_map: dict[int, FakeChannel] = {}
        self.owner_result = True

    async def get_prefix(self, _message):
        return "!"

    def get_command(self, name: str):
        for cog in self.cogs.values():
            for command in cog.get_commands():
                if command.name == name or name in command.aliases:
                    return command
        return None

    def get_cog(self, name: str):
        return self.cogs.get(name)

    async def is_owner(self, _author):
        return self.owner_result

    def reload_extension(self, extension: str):
        self.reloaded_extensions.append(extension)

    async def process_commands(self, message: FakeMessage):
        self.processed_messages.append(message)

    def get_channel(self, channel_id: int):
        return self.channel_map.get(channel_id)


class FakeContext:
    def __init__(
        self,
        bot: FakeBot,
        guild: FakeGuild | None = None,
        channel: FakeChannel | None = None,
        author: FakeUser | None = None,
        content: str = "!command",
        prefix: str = "!",
        mentions: list[FakeUser] | None = None,
    ):
        self.bot = bot
        self.guild = guild
        self.channel = channel or FakeChannel(1, guild=guild)
        self.author = author or FakeUser(1)
        self.prefix = prefix
        self.reply_messages: list[FakeSentMessage] = []
        self.message = FakeMessage(
            content=content,
            author=self.author,
            channel=self.channel,
            guild=self.guild,
            mentions=mentions,
        )

    async def send(self, content=None, embed=None, file=None):
        return await self.channel.send(content=content, embed=embed, file=file)

    async def reply(self, content=None, embed=None, file=None):
        message = await self.channel.send(content=content, embed=embed, file=file)
        self.reply_messages.append(message)
        return message


@pytest.fixture(autouse=True)
def reset_database_state():
    models.init_db()
    tables = [
        models.Reminder,
        models.AnimesNotifier,
        models.AnimesList,
        models.TwitchNotifier,
        models.Server,
        models.User,
        models.BotConfig,
    ]
    for table in tables:
        table.delete_all()

    yield

    models.rollback()
    for table in tables:
        table.delete_all()
    models.rollback()


def _make_ctx(
    bot: FakeBot | None = None,
    guild_id: int | None = 10,
    channel_id: int = 20,
    author_id: int = 30,
    content: str = "!command",
    mentions: list[FakeUser] | None = None,
) -> tuple[FakeBot, FakeContext]:
    bot = bot or FakeBot()
    guild = FakeGuild(guild_id) if guild_id is not None else None
    channel = FakeChannel(channel_id, guild=guild)
    if guild is not None:
        guild.add_channel(channel)
    bot.channel_map[channel.id] = channel
    ctx = FakeContext(
        bot=bot,
        guild=guild,
        channel=channel,
        author=FakeUser(author_id),
        content=content,
        mentions=mentions,
    )
    return bot, ctx


def _make_animes_cog(monkeypatch: pytest.MonkeyPatch, bot: FakeBot):
    class FakeAioJikan:
        def __init__(self, rate_limit=None):
            self.rate_limit = rate_limit

        async def search_anime(self, search_type, query):
            raise AssertionError(f"unexpected search_anime call for {query}")

        async def get_anime(self, mal_id):
            raise AssertionError(f"unexpected get_anime call for {mal_id}")

    monkeypatch.setattr(animes_module, "AioJikan", FakeAioJikan)
    return animes_module.AnimesCog(bot)


def _collect_defined_commands() -> set[str]:
    discovered: set[str] = set()
    for module in COG_MODULES:
        cog_name = module.__name__.split(".")[-1]
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if not issubclass(cls, commands.Cog):
                continue
            for member in cls.__dict__.values():
                if isinstance(member, commands.Command):
                    discovered.add(f"{cog_name}::{member.name}")
    return discovered


async def _run_ai_ask(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!ask Pergunta")
    cog = ai_module.AICog(bot)

    class FakeResponse:
        response = "Resposta da IA"

    ctx.channel.history_messages = [
        FakeMessage("mensagem anterior", FakeUser(55), ctx.channel, ctx.guild, 999),
    ]
    monkeypatch.setattr(ai_module, "generate_response", lambda messages: FakeResponse())

    await ai_module.AICog.ask.callback(cog, ctx, question="Como vai?")

    assert (
        ctx.channel.sent_messages[-1].content == "Resposta da IA"
    ), "ai::ask should return the AI response"


async def _run_ai_breakpoint(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!breakpoint")
    cog = ai_module.AICog(bot)

    await ai_module.AICog.breakpoint.callback(cog, ctx)

    assert ctx.message.reactions == [
        "👍"
    ], "ai::breakpoint should add the breakpoint reaction"


async def _run_ai_history(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!ai_history")
    cog = ai_module.AICog(bot)
    ctx.channel.history_messages = [
        FakeMessage(
            "mensagem do usuario",
            FakeUser(77, display_name="Alice"),
            ctx.channel,
            ctx.guild,
            998,
        ),
        FakeMessage("resposta do bot", bot.user, ctx.channel, ctx.guild, 997),
    ]

    await ai_module.AICog.ai_history.callback(cog, ctx)

    assert (
        "Histórico de mensagens" in ctx.channel.sent_messages[-1].content
    ), "ai::ai_history should render the collected AI history"


async def _run_animes_search_anime(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!search_anime frieren")
    cog = _make_animes_cog(monkeypatch, bot)
    script_calls = []

    class FakeScript:
        def __init__(self, name, function_name, time_out):
            script_calls.append((name, function_name, time_out))

        async def execute(self, **kwargs):
            script_calls.append(kwargs)

    async def fake_search_anime(search_type, query):
        return SimpleNamespace(data=[SimpleNamespace(mal_id=1, title="Frieren")])

    monkeypatch.setattr(animes_module, "Script", FakeScript)
    cog.jikan.search_anime = fake_search_anime

    await animes_module.AnimesCog.search_anime.callback(cog, ctx, anime="Frieren")

    assert (
        script_calls[0][1] == "search_anime"
    ), "animes::search_anime should execute the pagination script"
    assert (
        script_calls[1]["ctx"] is ctx
    ), "animes::search_anime should pass the command context to the script"


async def _run_animes_anime_list(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!anime_list")
    cog = _make_animes_cog(monkeypatch, bot)
    script_calls = []

    class FakeScript:
        def __init__(self, name, function_name, time_out):
            script_calls.append((name, function_name, time_out))

        async def execute(self, **kwargs):
            script_calls.append(kwargs)

    monkeypatch.setattr(animes_module, "Script", FakeScript)
    monkeypatch.setattr(
        animes_module.AnimesList,
        "get_user",
        lambda user_id: [SimpleNamespace(user_id=str(user_id), mal_id=1, dubbed=False)],
    )

    await animes_module.AnimesCog.anime_list.callback(cog, ctx, user=None)

    assert (
        script_calls[0][1] == "anime_list"
    ), "animes::anime_list should execute the watchlist script when entries exist"


async def _run_animes_add_anime(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!add_anime 100")
    cog = _make_animes_cog(monkeypatch, bot)

    async def fake_get_anime(mal_id):
        return SimpleNamespace(mal_id=mal_id, type="TV", title="Frieren")

    cog.jikan.get_anime = fake_get_anime

    await animes_module.AnimesCog.add_anime.callback(cog, ctx, mal_id=100, dubbed=False)

    stored = animes_module.AnimesList.get(
        user_id=ctx.author.id, mal_id=100, dubbed=False
    )
    assert stored is not None, "animes::add_anime should persist a watchlist entry"
    assert (
        "adicionado na lista" in ctx.channel.sent_messages[-1].content
    ), "animes::add_anime should confirm the insertion"


async def _run_animes_set_anime_lang(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!set_anime_lang en-us")
    cog = _make_animes_cog(monkeypatch, bot)

    await animes_module.AnimesCog.set_anime_lang.callback(cog, ctx, lang="en-us")

    user = animes_module.User.get_or_create(str(ctx.author.id))
    assert (
        user.anime_lang == "en-us"
    ), "animes::set_anime_lang should persist the selected language"


async def _run_animes_anime_channel(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!anime_channel")
    cog = _make_animes_cog(monkeypatch, bot)
    server = animes_module.Server.get_or_create(str(ctx.guild.id))
    server.set_anime_channel(str(ctx.channel.id))

    await animes_module.AnimesCog.anime_channel.callback(cog, ctx)

    assert (
        "Canal de notificação de animes" in ctx.channel.sent_messages[-1].content
    ), "animes::anime_channel should report the configured channel"


async def _run_animes_set_anime_channel(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!set_anime_channel")
    cog = _make_animes_cog(monkeypatch, bot)
    server = animes_module.Server.get_or_create(str(ctx.guild.id))
    target_channel = FakeChannel(55, name="anime-updates", guild=ctx.guild)

    await animes_module.AnimesCog.set_anime_channel.callback(
        cog, ctx, channel=target_channel
    )

    assert server.anime_channel == str(
        target_channel.id
    ), "animes::set_anime_channel should persist the target channel id"


async def _run_changelog_changelog(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!changelog")
    cog = changelog_module.ChangelogCog(bot)
    embed = Embed(title="Atualizacoes")

    monkeypatch.setattr(
        changelog_module.UpdateCollector,
        "get_last_n_commits",
        lambda limit: [SimpleNamespace(hash="abc123", date="2026-03-13")],
    )
    monkeypatch.setattr(
        changelog_module, "changelog_embed", lambda updates, color: embed
    )

    await changelog_module.ChangelogCog.changelog.callback(cog, ctx)

    assert (
        ctx.channel.sent_messages[-1].embed is embed
    ), "changelog::changelog should send the rendered changelog embed"


async def _run_changelog_set_channel(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!set_changelog_channel")
    cog = changelog_module.ChangelogCog(bot)

    await changelog_module.ChangelogCog.set_changelog_channel.callback(cog, ctx)

    server = changelog_module.Server.get_or_create(str(ctx.guild.id))
    assert server.changelog_channel == str(
        ctx.channel.id
    ), "changelog::set_changelog_channel should persist the channel id"


async def _run_changelog_remove_channel(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!remove_changelog_channel")
    cog = changelog_module.ChangelogCog(bot)
    server = changelog_module.Server.get_or_create(str(ctx.guild.id))
    server.changelog_channel = str(ctx.channel.id)
    server.update()

    await changelog_module.ChangelogCog.remove_changelog_channel.callback(cog, ctx)

    refreshed = changelog_module.Server.get_or_create(str(ctx.guild.id))
    assert (
        refreshed.changelog_channel is None
    ), "changelog::remove_changelog_channel should clear the configured channel"


async def _run_changelog_channel(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!changelog_channel")
    cog = changelog_module.ChangelogCog(bot)
    server = changelog_module.Server.get_or_create(str(ctx.guild.id))
    server.changelog_channel = str(ctx.channel.id)
    server.update()

    await changelog_module.ChangelogCog.changelog_channel.callback(cog, ctx)

    assert (
        "canal de changelog" in ctx.channel.sent_messages[-1].content.lower()
    ), "changelog::changelog_channel should describe the configured channel"


async def _run_core_ping(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!ping")
    cog = core_module.CoreCog(bot)
    values = iter([0.0, 0.123])
    monkeypatch.setattr(core_module, "time", lambda: next(values))

    await core_module.CoreCog.ping.callback(cog, ctx)

    assert (
        ctx.channel.sent_messages[0].edits[-1]["content"] == "`123ms` Pong!"
    ), "core::ping should edit the probe message with latency"


async def _run_core_prefix(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!prefix")
    cog = core_module.CoreCog(bot)

    await core_module.CoreCog.prefix.callback(cog, ctx)

    assert (
        "prefixo do servidor" in ctx.channel.sent_messages[-1].content.lower()
    ), "core::prefix should disclose the active prefix"


async def _run_core_current_time(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!current_time")
    cog = core_module.CoreCog(bot)
    timezone = pytz.timezone("UTC")
    monkeypatch.setattr(
        core_module.Server,
        "get",
        lambda guild_id: SimpleNamespace(get_timezone=lambda: timezone),
    )

    await core_module.CoreCog.current_time.callback(cog, ctx)

    assert (
        "[UTC]" in ctx.reply_messages[-1].content
    ), "core::current_time should include the resolved timezone in the response"


async def _run_core_say(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!say ola")
    cog = core_module.CoreCog(bot)

    await core_module.CoreCog.say.callback(cog, ctx, content="ola")

    assert (
        ctx.channel.sent_messages[-1].content == "ola"
    ), "core::say should repeat the provided content"


async def _run_core_upchat(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!upchat")
    cog = core_module.CoreCog(bot)

    await core_module.CoreCog.up_chat.callback(cog, ctx)

    assert (
        ctx.channel.sent_messages[-1].content.count("** **") == 50
    ), "core::upchat should push the chat with 50 blank lines"


async def _run_debug_reload(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!reload")
    bot.extensions = {"juliabot.cogs.core": object(), "juliabot.cogs.help": object()}
    cog = debug_module.DebugCog(bot)

    await debug_module.DebugCog.reload_cogs.callback(cog, ctx)

    assert bot.reloaded_extensions == [
        "juliabot.cogs.core",
        "juliabot.cogs.help",
    ], "debug::reload should request reload for each registered extension"
    assert (
        ctx.channel.sent_messages[0].content == "Cogs regarregados com sucesso!"
    ), "debug::reload should finalize the progress message"


async def _run_debug_scripts(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!scripts")
    cog = debug_module.DebugCog(bot)
    monkeypatch.setattr(debug_module.Script, "get_scripts", lambda: [])

    await debug_module.DebugCog.get_all_scripts.callback(cog, ctx)

    assert (
        ctx.channel.sent_messages[-1].content == "Nenhum script rodando no momento."
    ), "debug::scripts should explain when there are no live scripts"


async def _run_debug_exec(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!exec ping")
    cog = debug_module.DebugCog(bot)
    target_user = FakeUser(404, display_name="executor")

    await debug_module.DebugCog.exec_as_user.callback(
        cog, ctx, user=target_user, command="ping"
    )

    assert (
        bot.processed_messages[-1].author is target_user
    ), "debug::exec should impersonate the requested user"
    assert (
        bot.processed_messages[-1].content == "!ping"
    ), "debug::exec should rebuild the command content with the original prefix"


async def _run_fun_duel(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    challenged = FakeUser(808, display_name="rival")
    bot, ctx = _make_ctx(content="!duel", mentions=[challenged])
    cog = fun_module.FunCog(bot)
    script_calls = []

    class FakeScript:
        def __init__(self, name, function_name):
            script_calls.append((name, function_name))

        async def execute(self, **kwargs):
            script_calls.append(kwargs)

    monkeypatch.setattr(fun_module, "Script", FakeScript)

    await fun_module.FunCog.duel.callback(cog, ctx, user=challenged)

    assert script_calls[0] == (
        f"duel_{ctx.guild.id}",
        "duel",
    ), "fun::duel should start the duel script with a guild-scoped key"


async def _run_fun_dice(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!dice 3")
    cog = fun_module.FunCog(bot)
    monkeypatch.setattr(fun_module, "shuffle", lambda values: None)
    monkeypatch.setattr(fun_module, "randint", lambda _start, end: end)
    monkeypatch.setattr(fun_module.time, "sleep", lambda _seconds: None)

    await fun_module.FunCog.dice.callback(cog, ctx, args="3")

    assert (
        ctx.channel.sent_messages[0].content == "Resultado: 3 :game_die:"
    ), "fun::dice should end by editing the roll message with the final result"


async def _run_game_startgame(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!startgame")
    cog = game_module.GameCog(bot)
    monkeypatch.setattr(
        game_module,
        "generate_response",
        lambda *args, **kwargs: SimpleNamespace(response="Inicio"),
    )

    await game_module.GameCog.start_game.callback(cog, ctx, seed="seed")

    assert (
        ctx.channel.sent_messages[-1].content == "Inicio"
    ), "game::startgame should send the generated opening scene"
    assert (
        ctx.channel.id in cog.sessions
    ), "game::startgame should create a session for the channel"


async def _run_game_play(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!play abrir porta")
    cog = game_module.GameCog(bot)
    cog.sessions[ctx.channel.id] = game_module.GameSession(ctx.channel.id)
    monkeypatch.setattr(
        game_module,
        "generate_response",
        lambda *args, **kwargs: SimpleNamespace(
            game_response="Voce entrou", grammar_correction="You entered"
        ),
    )

    await game_module.GameCog.play.callback(cog, ctx, action="abrir porta")

    assert (
        "Grammar Correction" in ctx.channel.sent_messages[-1].content
    ), "game::play should include grammar feedback when available"


async def _run_game_endgame(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!endgame")
    cog = game_module.GameCog(bot)
    cog.sessions[ctx.channel.id] = game_module.GameSession(ctx.channel.id)

    await game_module.GameCog.end_game.callback(cog, ctx)

    assert (
        ctx.channel.id not in cog.sessions
    ), "game::endgame should remove the session from memory"


async def _run_help_help(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!help")
    core_cog = core_module.CoreCog(bot)
    help_cog = help_module.HelpCog(bot)
    bot.cogs = {"core": core_cog, "help": help_cog}

    await help_module.HelpCog.help.callback(help_cog, ctx, argument=None)

    assert (
        ctx.channel.sent_messages[-1].embed.title == "Lista de Comandos"
    ), "help::help should render the global help embed"


async def _run_reminder_list(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!list_reminders")
    cog = reminder_module._ReminderCog(bot)
    script_calls = []

    class FakeScript:
        def __init__(self, name, function_name, time_out):
            script_calls.append((name, function_name, time_out))

        async def execute(self, **kwargs):
            script_calls.append(kwargs)

    monkeypatch.setattr(reminder_module, "Script", FakeScript)
    monkeypatch.setattr(
        reminder_module.Reminder,
        "get_all",
        lambda user_id: [SimpleNamespace(user_id=str(user_id))],
    )

    await reminder_module._ReminderCog.list_reminders.callback(cog, ctx)

    assert (
        script_calls[0][1] == "list_reminders"
    ), "reminder::list_reminders should execute the interactive reminder script"


async def _run_reminder_remind_me(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!remind_me")
    cog = reminder_module._ReminderCog(bot)
    target_date = datetime(2026, 3, 14, 12, 0, tzinfo=pytz.utc)

    await reminder_module._ReminderCog.remind_me.callback(cog, ctx, date=target_date)

    reminders = reminder_module.Reminder.get_all(ctx.author.id)
    assert len(reminders) == 1, "reminder::remind_me should persist the reminder entry"
    assert (
        "OK, Eu irei te notificar" in ctx.reply_messages[-1].content
    ), "reminder::remind_me should acknowledge the scheduled reminder"


async def _run_reminder_remind_me_loop(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!remind_me_loop 2h")
    cog = reminder_module._ReminderCog(bot)
    target_date = datetime(2026, 3, 14, 13, 0, tzinfo=pytz.utc)

    async def fake_convert(_self, _ctx, argument):
        assert argument == "2h"
        return target_date

    monkeypatch.setattr(reminder_module.DeltaToDate, "convert", fake_convert)

    await reminder_module._ReminderCog.remind_me_loop.callback(cog, ctx, arg="2h")

    reminders = reminder_module.Reminder.get_all(ctx.author.id)
    assert (
        len(reminders) == 1
    ), "reminder::remind_me_loop should create a recurring reminder entry"


async def _run_server_config_set_prefix(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!set_prefix ?")
    cog = server_config_module.ServerConfigCog(bot)

    await server_config_module.ServerConfigCog.set_prefix.callback(cog, ctx, prefix="?")

    server = server_config_module.Server.get_or_create(str(ctx.guild.id))
    assert (
        server.prefix == "?"
    ), "server_config::set_prefix should persist the new prefix"


async def _run_server_config_set_timezone(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!set_timezone UTC")
    cog = server_config_module.ServerConfigCog(bot)

    await server_config_module.ServerConfigCog.set_timezone.callback(
        cog, ctx, timezone="UTC"
    )

    server = server_config_module.Server.get_or_create(str(ctx.guild.id))
    assert (
        server.timezone == "UTC"
    ), "server_config::set_timezone should persist the selected timezone"


async def _run_twitch_stream(monkeypatch: pytest.MonkeyPatch, _tmp_path: Path) -> None:
    bot, ctx = _make_ctx(content="!stream streamer")
    cog = twitch_module.TwitchCog(bot)
    monkeypatch.setattr(
        twitch_module.TwitchCog, "is_streamer_online", lambda streamer: True
    )

    await twitch_module.TwitchCog.stream.callback(cog, ctx, streamer="streamer")

    assert (
        "online" in ctx.channel.sent_messages[-1].content
    ), "twitch::stream should report the streamer status"


async def _run_twitch_add_streamer(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!add_streamer streamer")
    cog = twitch_module.TwitchCog(bot)

    await twitch_module.TwitchCog.add_streamer.callback(cog, ctx, streamer="streamer")

    assert (
        twitch_module.TwitchNotifier.get("streamer", str(ctx.channel.id)) is not None
    ), "twitch::add_streamer should persist the subscription"


async def _run_twitch_remove_streamer(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!remove_streamer streamer")
    cog = twitch_module.TwitchCog(bot)
    twitch_module.TwitchNotifier("streamer", str(ctx.channel.id))

    await twitch_module.TwitchCog.remove_streamer.callback(
        cog, ctx, streamer="streamer"
    )

    assert (
        twitch_module.TwitchNotifier.get("streamer", str(ctx.channel.id)) is None
    ), "twitch::remove_streamer should delete the existing subscription"


async def _run_twitch_list_streamers(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!list_streamers")
    cog = twitch_module.TwitchCog(bot)
    twitch_module.TwitchNotifier("one", str(ctx.channel.id))
    twitch_module.TwitchNotifier("two", str(ctx.channel.id))

    await twitch_module.TwitchCog.list_streamers.callback(cog, ctx)

    assert (
        "one" in ctx.channel.sent_messages[-1].content
        and "two" in ctx.channel.sent_messages[-1].content
    ), "twitch::list_streamers should enumerate the tracked streamers"


async def _run_twitch_reset_notifications(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!reset_notifications")
    cog = twitch_module.TwitchCog(bot)
    notifier = twitch_module.TwitchNotifier("streamer", str(ctx.channel.id))
    notifier.notified = True
    notifier.update()

    await twitch_module.TwitchCog.reset_notifications.callback(cog, ctx)

    assert (
        twitch_module.TwitchNotifier.get("streamer", str(ctx.channel.id)).notified
        is False
    ), "twitch::reset_notifications should clear the notification flag"


async def _run_utilities_translate(
    monkeypatch: pytest.MonkeyPatch, _tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!translate en hello")
    cog = utilities_module.UtilitiesCog(bot)

    class FakeTranslator:
        def __init__(self, source=None, target=None):
            self.source = source
            self.target = target

        def is_language_supported(self, lang):
            return lang == "en"

        def translate(self, text):
            return f"translated:{text}:{self.target}"

    monkeypatch.setattr(utilities_module, "GoogleTranslator", FakeTranslator)

    await utilities_module.UtilitiesCog.translate.callback(
        cog, ctx, args="en ola mundo"
    )

    assert (
        ctx.channel.sent_messages[-1].content == "translated:ola mundo:en"
    ), "utilities::translate should send the translated text"


async def _run_utilities_channel_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bot, ctx = _make_ctx(content="!channel_history")
    cog = utilities_module.UtilitiesCog(bot)

    history_message = SimpleNamespace(
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=pytz.utc),
        guild=SimpleNamespace(name="Guild"),
        channel=SimpleNamespace(name="general"),
        author="Alice",
        content="hello",
    )
    ctx.channel.history_messages = [history_message]
    monkeypatch.setattr(
        utilities_module, "File", lambda path: SimpleNamespace(path=path)
    )
    monkeypatch.chdir(tmp_path)

    await utilities_module.UtilitiesCog.channel_history.callback(
        cog, ctx, channel=None, start=None, end=None
    )

    assert (
        ctx.channel.sent_messages[0].deleted is True
    ), "utilities::channel_history should delete the progress message after finishing"
    assert (
        ctx.channel.sent_messages[-1].file.path == "channel_history.txt"
    ), "utilities::channel_history should send the generated transcript file"


COMMAND_CASES = [
    CommandCase("ai", "ask", _run_ai_ask),
    CommandCase("ai", "breakpoint", _run_ai_breakpoint),
    CommandCase("ai", "ai_history", _run_ai_history),
    CommandCase("animes", "search_anime", _run_animes_search_anime),
    CommandCase("animes", "anime_list", _run_animes_anime_list),
    CommandCase("animes", "add_anime", _run_animes_add_anime),
    CommandCase("animes", "set_anime_lang", _run_animes_set_anime_lang),
    CommandCase("animes", "anime_channel", _run_animes_anime_channel),
    CommandCase("animes", "set_anime_channel", _run_animes_set_anime_channel),
    CommandCase("changelog", "changelog", _run_changelog_changelog),
    CommandCase("changelog", "set_changelog_channel", _run_changelog_set_channel),
    CommandCase("changelog", "remove_changelog_channel", _run_changelog_remove_channel),
    CommandCase("changelog", "changelog_channel", _run_changelog_channel),
    CommandCase("core", "ping", _run_core_ping),
    CommandCase("core", "prefix", _run_core_prefix),
    CommandCase("core", "current_time", _run_core_current_time),
    CommandCase("core", "say", _run_core_say),
    CommandCase("core", "upchat", _run_core_upchat),
    CommandCase("debug", "reload", _run_debug_reload),
    CommandCase("debug", "scripts", _run_debug_scripts),
    CommandCase("debug", "exec", _run_debug_exec),
    CommandCase("fun", "duel", _run_fun_duel),
    CommandCase("fun", "dice", _run_fun_dice),
    CommandCase("game", "startgame", _run_game_startgame),
    CommandCase("game", "play", _run_game_play),
    CommandCase("game", "endgame", _run_game_endgame),
    CommandCase("help", "help", _run_help_help),
    CommandCase("reminder", "list_reminders", _run_reminder_list),
    CommandCase("reminder", "remind_me", _run_reminder_remind_me),
    CommandCase("reminder", "remind_me_loop", _run_reminder_remind_me_loop),
    CommandCase("server_config", "set_prefix", _run_server_config_set_prefix),
    CommandCase("server_config", "set_timezone", _run_server_config_set_timezone),
    CommandCase("twitch", "stream", _run_twitch_stream),
    CommandCase("twitch", "add_streamer", _run_twitch_add_streamer),
    CommandCase("twitch", "remove_streamer", _run_twitch_remove_streamer),
    CommandCase("twitch", "list_streamers", _run_twitch_list_streamers),
    CommandCase("twitch", "reset_notifications", _run_twitch_reset_notifications),
    CommandCase("utilities", "translate", _run_utilities_translate),
    CommandCase("utilities", "channel_history", _run_utilities_channel_history),
]


def test_all_cog_commands_have_explicit_test_cases():
    discovered = _collect_defined_commands()
    covered = {case.id for case in COMMAND_CASES}

    missing = sorted(discovered - covered)
    extra = sorted(covered - discovered)

    assert not missing and not extra, (
        "Cog command coverage drift detected. "
        f"Missing cases: {missing}. Extra cases: {extra}."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("case", COMMAND_CASES, ids=lambda case: case.id)
async def test_cog_command_smoke_cases(
    case: CommandCase, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    await case.runner(monkeypatch, tmp_path)
