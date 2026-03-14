#!/usr/bin/env python3
"""End-to-End Tester Bot for JuliaBot.

This bot runs automated tests against JuliaBot by sending commands and validating
responses in a specified Discord channel. It is designed to be run in a controlled environment
to ensure that JuliaBot's core functionalities are working as expected.

Usage:
    Requires two Discord bot tokens:
    - DISCORD_TOKEN: Main bot token (in .env)
    - E2E_TESTER_BOT_TOKEN: Tester bot token (in .env)

    Run:
        python scripts/e2e_tester.py
"""

import asyncio
import inspect
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Pattern

import discord
from discord.ext import commands
from environs import Env

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment
env = Env()
env.read_env()


prefix = env.str("E2E_COMMAND_PREFIX", env.str("PREFIX", "!"))

E2E_AI_PROMPT = env.str("E2E_AI_PROMPT", "Responda com uma saudação curta.")
E2E_ANIME_QUERY = env.str("E2E_ANIME_QUERY", "Frieren")
E2E_ANIME_MAL_ID = env.str("E2E_ANIME_MAL_ID", "1")
E2E_GAME_ACTION = env.str("E2E_GAME_ACTION", "olhar em volta")
E2E_GAME_SEED = env.str("E2E_GAME_SEED", "floresta misteriosa")
E2E_REMINDER_DATE = env.str("E2E_REMINDER_DATE", "31/12/2099")
E2E_REMINDER_LOOP = env.str("E2E_REMINDER_LOOP", "1h")
E2E_SAY_TEXT = env.str("E2E_SAY_TEXT", "e2e say ok")
E2E_STREAMER = env.str("E2E_STREAMER", "ninja")
E2E_TIMEZONE = env.str("E2E_TIMEZONE", "UTC")
E2E_TRANSLATE_LANG = env.str("E2E_TRANSLATE_LANG", "en")
E2E_TRANSLATE_TEXT = env.str("E2E_TRANSLATE_TEXT", "ola mundo")


def rx(pattern: str) -> Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class ObservedEvent:
    """Normalized event observed while waiting for the target bot response."""

    kind: str
    message: Optional[discord.Message] = None
    emoji: Optional[str] = None
    user_id: Optional[int] = None


@dataclass(frozen=True)
class E2ETestCase:
    """Declarative structure for an end-to-end command test."""

    cog: str
    command: str
    description: str
    send_text: str | Callable[["E2ETester"], str]
    expected_response: Optional[Pattern[str]] = None
    expected_embed: Optional[Pattern[str]] = None
    expected_reaction: Optional[str] = None
    timeout_seconds: float = 10.0
    validator: Optional[Callable[[ObservedEvent], bool]] = None
    before_messages: tuple[str, ...] = ()


@dataclass
class TestStats:
    """Tracks cumulative status for a single test run."""

    passed: int = 0
    failed: int = 0


@dataclass
class SingleTestResult:
    """Detailed execution outcome for one E2E test case."""

    test: E2ETestCase
    passed: bool
    reason: str
    attempts: int
    duration_seconds: float
    sent_command: str
    response_preview: Optional[str] = None
    mismatch_reasons: list[str] = field(default_factory=list)


def _embed_text(message: discord.Message) -> str:
    parts: list[str] = []
    for embed in message.embeds:
        parts.extend([embed.title or "", embed.description or ""])
        parts.extend(field.name or "" for field in embed.fields)
        parts.extend(field.value or "" for field in embed.fields)
    return "\n".join(parts)


def _has_text(event: ObservedEvent) -> bool:
    return (
        event.kind == "message"
        and event.message is not None
        and bool((event.message.content or "").strip())
    )


def _has_embed(event: ObservedEvent) -> bool:
    return (
        event.kind == "message"
        and event.message is not None
        and bool(event.message.embeds)
    )


def _has_attachment(event: ObservedEvent, filename: str | None = None) -> bool:
    if (
        event.kind != "message"
        or event.message is None
        or not event.message.attachments
    ):
        return False
    if filename is None:
        return True
    return any(
        attachment.filename == filename for attachment in event.message.attachments
    )


def _any_of(
    *validators: Callable[[ObservedEvent], bool]
) -> Callable[[ObservedEvent], bool]:
    return lambda event: any(validator(event) for validator in validators)


def _text_matches(pattern: Pattern[str]) -> Callable[[ObservedEvent], bool]:
    return lambda event: (
        event.kind == "message"
        and event.message is not None
        and bool(pattern.search(event.message.content or ""))
    )


def _render_command_text(value: str) -> str:
    return value if value.startswith(prefix) else f"{prefix}{value}"


def _current_channel_command(command_name: str) -> Callable[["E2ETester"], str]:
    def _factory(tester: "E2ETester") -> str:
        if tester.test_channel is None:
            raise RuntimeError("Test channel is not initialized.")
        return f"{command_name} {tester.test_channel.mention}"

    return _factory


def _duel_self_command(tester: "E2ETester") -> str:
    if tester.user is None:
        raise RuntimeError("Tester bot user is not ready yet.")
    return f"duel {tester.user.mention}"


def _exec_self_ping_command(tester: "E2ETester") -> str:
    if tester.user is None:
        raise RuntimeError("Tester bot user is not ready yet.")
    return f"exec {tester.user.mention} ping"


test_cases = [
    E2ETestCase(
        cog="help",
        command="help",
        description="Render the top-level help embed.",
        send_text="help",
        expected_embed=rx(r"lista de comandos"),
    ),
    E2ETestCase(
        cog="core",
        command="ping",
        description="Check that ping returns a latency response.",
        send_text="ping",
        expected_response=rx(r"ping|pong|\d+ms"),
    ),
    E2ETestCase(
        cog="core",
        command="prefix",
        description="Read the server prefix.",
        send_text="prefix",
        expected_response=rx(r"prefixo do servidor"),
    ),
    E2ETestCase(
        cog="core",
        command="current_time",
        description="Read the current server time.",
        send_text="current_time",
        expected_response=rx(r"A hora atual do servidor"),
    ),
    E2ETestCase(
        cog="core",
        command="say",
        description="Echo a controlled phrase.",
        send_text=f"say {E2E_SAY_TEXT}",
        expected_response=rx(re.escape(E2E_SAY_TEXT)),
    ),
    E2ETestCase(
        cog="core",
        command="upchat",
        description="Push the chat if the tester has admin permission.",
        send_text="upchat",
        expected_response=rx(r"\*\* \*\*|Você não tem permissão"),
    ),
    E2ETestCase(
        cog="ai",
        command="breakpoint",
        description="Add a breakpoint marker to AI history.",
        send_text="breakpoint",
        expected_reaction="👍",
        timeout_seconds=15.0,
    ),
    E2ETestCase(
        cog="ai",
        command="ai_history",
        description="Show AI history using recent channel messages.",
        send_text="ai_history",
        expected_response=rx(
            r"Histórico de mensagens para a IA|Nenhuma mensagem recente encontrada"
        ),
        before_messages=("mensagem de aquecimento para o histórico da IA",),
    ),
    E2ETestCase(
        cog="ai",
        command="ask",
        description="Send a short AI prompt and accept a regular reply or handled error.",
        send_text=f"ask {E2E_AI_PROMPT}",
        validator=_has_text,
        timeout_seconds=45.0,
    ),
    E2ETestCase(
        cog="animes",
        command="search_anime",
        description="Search an anime title and accept an embed or an explanatory failure.",
        send_text=f"search_anime {E2E_ANIME_QUERY}",
        validator=_any_of(
            _has_embed,
            _text_matches(rx(r"Não foi encontrado nenhum anime|Erro:")),
        ),
        timeout_seconds=30.0,
    ),
    E2ETestCase(
        cog="animes",
        command="add_anime",
        description="Add a MAL entry to the anime list.",
        send_text=f"add_anime {E2E_ANIME_MAL_ID}",
        expected_response=rx(
            r"adicionado na lista|já está na lista|Não foi encontrado nenhum anime|Erro:"
        ),
        timeout_seconds=30.0,
    ),
    E2ETestCase(
        cog="animes",
        command="anime_list",
        description="List anime subscriptions after the add attempt.",
        send_text="anime_list",
        validator=_any_of(
            _has_embed,
            _text_matches(
                rx(r"não tem nenhum anime na lista|A lista de animes está vazia")
            ),
        ),
        timeout_seconds=30.0,
    ),
    E2ETestCase(
        cog="animes",
        command="set_anime_lang",
        description="Set a supported anime language preference.",
        send_text="set_anime_lang en-us",
        expected_response=rx(
            r"Linguagem de animes configurada|Lingua inválida|Língua inválida"
        ),
    ),
    E2ETestCase(
        cog="animes",
        command="set_anime_channel",
        description="Configure the current channel for anime notifications.",
        send_text=_current_channel_command("set_anime_channel"),
        expected_response=rx(
            r"Canal de notificações de anime configurado|Notificações de animes desabilitadas|Você não tem permissão"
        ),
    ),
    E2ETestCase(
        cog="animes",
        command="anime_channel",
        description="Read back the anime notification channel.",
        send_text="anime_channel",
        expected_response=rx(
            r"Canal de notificação de animes|não possui nenhum canal de notificações de animes"
        ),
    ),
    E2ETestCase(
        cog="changelog",
        command="changelog",
        description="Render the changelog output.",
        send_text="changelog",
        validator=_any_of(
            _has_embed,
            _text_matches(rx(r"Nenhuma atualização encontrada")),
        ),
        timeout_seconds=20.0,
    ),
    E2ETestCase(
        cog="changelog",
        command="set_changelog_channel",
        description="Set the current channel as changelog target.",
        send_text="set_changelog_channel",
        expected_response=rx(r"Canal de changelog definido"),
    ),
    E2ETestCase(
        cog="changelog",
        command="changelog_channel",
        description="Read back the configured changelog channel.",
        send_text="changelog_channel",
        expected_response=rx(
            r"canal de changelog automático é|Nenhum canal de changelog automático definido|não existe mais"
        ),
    ),
    E2ETestCase(
        cog="changelog",
        command="remove_changelog_channel",
        description="Remove the configured changelog channel.",
        send_text="remove_changelog_channel",
        expected_response=rx(r"Canal de changelog automático removido"),
    ),
    E2ETestCase(
        cog="fun",
        command="duel",
        description="Start a duel against the tester bot itself.",
        send_text=_duel_self_command,
        expected_response=rx(r"desafia .* para um duelo"),
    ),
    E2ETestCase(
        cog="fun",
        command="dice",
        description="Roll a six-sided die.",
        send_text="dice 6",
        expected_response=rx(r"Resultado:|:game_die:"),
        timeout_seconds=15.0,
    ),
    E2ETestCase(
        cog="game",
        command="play",
        description="Exercise the no-session branch before starting a game.",
        send_text=f"play {E2E_GAME_ACTION}",
        expected_response=rx(r"Nenhuma sessão de jogo ativa|Grammar Correction|Erro:"),
        timeout_seconds=30.0,
    ),
    E2ETestCase(
        cog="game",
        command="startgame",
        description="Start a text adventure session.",
        send_text=f"startgame {E2E_GAME_SEED}",
        validator=_has_text,
        timeout_seconds=45.0,
    ),
    E2ETestCase(
        cog="game",
        command="endgame",
        description="Close the running game session when available.",
        send_text="endgame",
        expected_response=rx(
            r"Sessão de jogo encerrada|Nenhuma sessão de jogo ativa para encerrar"
        ),
    ),
    E2ETestCase(
        cog="reminder",
        command="remind_me",
        description="Create a one-shot reminder.",
        send_text=f"remind_me {E2E_REMINDER_DATE}",
        expected_response=rx(r"OK, Eu irei te notificar"),
    ),
    E2ETestCase(
        cog="reminder",
        command="remind_me_loop",
        description="Create a recurring reminder.",
        send_text=f"remind_me_loop {E2E_REMINDER_LOOP}",
        expected_response=rx(
            r"OK, Eu irei te notificar dia|Por favor, use um formato de data válido"
        ),
    ),
    E2ETestCase(
        cog="reminder",
        command="list_reminders",
        description="List existing reminders.",
        send_text="list_reminders",
        validator=_any_of(
            _has_embed,
            _text_matches(rx(r"Você não tem nenhum lembrete")),
        ),
    ),
    E2ETestCase(
        cog="twitch",
        command="stream",
        description="Check the status of a configured streamer.",
        send_text=f"stream {E2E_STREAMER}",
        expected_response=rx(r"está online|está offline|Erro ao acessar"),
        timeout_seconds=20.0,
    ),
    E2ETestCase(
        cog="twitch",
        command="add_streamer",
        description="Add a streamer notification for the current channel.",
        send_text=f"add_streamer {E2E_STREAMER}",
        expected_response=rx(
            r"foi adicionado para notificação|já está recebendo notificações"
        ),
    ),
    E2ETestCase(
        cog="twitch",
        command="list_streamers",
        description="List streamers tracked in the current channel.",
        send_text="list_streamers",
        expected_response=rx(
            r"Streamers notificados neste canal|Nenhum streamer está sendo notificado"
        ),
    ),
    E2ETestCase(
        cog="twitch",
        command="reset_notifications",
        description="Reset streamer notification flags.",
        send_text="reset_notifications",
        expected_response=rx(r"As notificações de streamers foram resetadas"),
    ),
    E2ETestCase(
        cog="twitch",
        command="remove_streamer",
        description="Remove the streamer notification for the current channel.",
        send_text=f"remove_streamer {E2E_STREAMER}",
        expected_response=rx(
            r"foi removido da lista de notificação|não está na lista de notificação"
        ),
    ),
    E2ETestCase(
        cog="utilities",
        command="translate",
        description="Translate a short sentence.",
        send_text=f"translate {E2E_TRANSLATE_LANG} {E2E_TRANSLATE_TEXT}",
        validator=_has_text,
        timeout_seconds=30.0,
    ),
    E2ETestCase(
        cog="utilities",
        command="channel_history",
        description="Export channel history to a text file.",
        send_text="channel_history",
        validator=lambda event: _has_attachment(event, "channel_history.txt"),
        timeout_seconds=30.0,
    ),
    E2ETestCase(
        cog="debug",
        command="reload",
        description="Reload cogs if the tester user is the bot owner.",
        send_text="reload",
        expected_response=rx(r"The check functions for command reload failed"),
    ),
    E2ETestCase(
        cog="debug",
        command="scripts",
        description="Inspect running scripts when owner access is available.",
        send_text="scripts",
        expected_response=rx(r"The check functions for command reload failed"),
    ),
    E2ETestCase(
        cog="debug",
        command="exec",
        description="Execute ping as another user when owner access is available.",
        send_text=_exec_self_ping_command,
        expected_response=rx(r"The check functions for command reload failed"),
    ),
    E2ETestCase(
        cog="server_config",
        command="set_prefix",
        description="Keep the command prefix aligned with the suite prefix.",
        send_text=f"set_prefix {prefix}",
        expected_response=rx(r"Prefixo de comandos mudado para|Você não tem permissão"),
    ),
    E2ETestCase(
        cog="server_config",
        command="set_timezone",
        description="Set the server timezone to a deterministic value.",
        send_text=f"set_timezone {E2E_TIMEZONE}",
        expected_response=rx(
            r"Fuso horário mudado para|Você não tem permissão|não é válido"
        ),
    ),
]


def event_matches_test(event: ObservedEvent, test: E2ETestCase) -> bool:
    """Return True when an observed event satisfies the expected outcome."""
    if event.kind == "message" and event.message is not None:
        if test.expected_response and test.expected_response.search(
            event.message.content or ""
        ):
            return True

        if test.expected_embed and event.message.embeds:
            embed_text = _embed_text(event.message)
            logger.debug(
                "Checking embed text for '%s': %s | pattern=%s",
                test.command,
                embed_text,
                test.expected_embed.pattern,
            )
            if test.expected_embed.search(embed_text):
                return True

    if test.expected_reaction and event.kind == "reaction":
        return event.emoji == test.expected_reaction

    if test.validator is not None:
        result = test.validator(event)
        if inspect.isawaitable(result):
            logger.warning(
                "Async validators are not supported for test '%s'.", test.command
            )
            return False
        return bool(result)

    return False


class E2ETester(commands.Bot):
    """End-to-End Tester Bot for JuliaBot."""

    def __init__(self, verbose: bool = False):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

        self.verbose = verbose
        self.results = TestStats()
        self.test_history: list[SingleTestResult] = []
        self.running_tests = False
        self.test_channel: Optional[discord.TextChannel] = None
        self.target_bot_id = env.int("TARGET_BOT_ID", None)

    async def on_ready(self):
        logger.info(f"{self.user} has connected to Discord!")

    def _is_expected_response_author(self, message: discord.Message) -> bool:
        """Filter out unrelated messages to reduce false positives in busy channels."""
        if message.author == self.user:
            return False

        if self.test_channel is not None and message.channel != self.test_channel:
            return False

        if self.target_bot_id is not None and message.author.id != self.target_bot_id:
            return False

        return True

    @staticmethod
    def _is_expected_reaction_actor(
        reaction: discord.Reaction,
        user: discord.abc.User,
        test_channel: Optional[discord.TextChannel],
        self_user: discord.ClientUser | None,
        target_bot_id: Optional[int],
    ) -> bool:
        if self_user is not None and user == self_user:
            return False

        if test_channel is not None and reaction.message.channel != test_channel:
            return False

        if self_user is not None and reaction.message.author != self_user:
            return False

        if target_bot_id is not None and user.id != target_bot_id:
            return False

        return True

    @staticmethod
    def _format_response_preview(message: discord.Message) -> str:
        """Create a compact human-readable response summary for test logs."""
        if message.content:
            return message.content

        if message.attachments:
            names = ", ".join(attachment.filename for attachment in message.attachments)
            return f"[attachments] {names}"

        if message.embeds:
            first_embed = message.embeds[0]
            title = first_embed.title or "(no title)"
            description = first_embed.description or "(no description)"
            return f"[embed] {title} | {description}"

        return "[empty message]"

    def _event_preview(self, event: ObservedEvent) -> str:
        if event.kind == "reaction":
            return f"[reaction] {event.emoji} by {event.user_id}"
        if event.message is None:
            return "[unknown event]"
        return self._format_response_preview(event.message)

    @staticmethod
    def _truncate_text(text: str, limit: int = 160) -> str:
        """Keep report text concise so messages stay readable in Discord."""
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."

    @staticmethod
    def _expectation_summary(test: E2ETestCase) -> str:
        """Summarize expectation criteria for diagnostics."""
        parts = []
        if test.expected_response:
            parts.append(f"text /{test.expected_response.pattern}/")
        if test.expected_embed:
            parts.append(f"embed /{test.expected_embed.pattern}/")
        if test.expected_reaction:
            parts.append(f"reaction {test.expected_reaction}")
        if test.validator is not None:
            parts.append("custom validator")

        if not parts:
            return "no expectation defined"
        return " + ".join(parts)

    def _event_mismatch_reason(self, event: ObservedEvent, test: E2ETestCase) -> str:
        """Explain why a candidate event did not satisfy the test."""
        checks = []

        if event.kind == "reaction":
            if test.expected_reaction:
                checks.append(
                    "reaction matched"
                    if event.emoji == test.expected_reaction
                    else f"reaction {event.emoji!r} did not match"
                )
            else:
                checks.append("unexpected reaction event")

            if test.validator is not None:
                checks.append("validator rejected event")

            return ", ".join(checks)

        message = event.message
        if message is None:
            return "event had no message payload"

        if test.expected_response:
            if test.expected_response.search(message.content or ""):
                checks.append("text matched")
            else:
                checks.append("text did not match")

        if test.expected_embed:
            if not message.embeds:
                checks.append("embed missing")
            else:
                checks.append(
                    "embed matched"
                    if test.expected_embed.search(_embed_text(message))
                    else "embed did not match"
                )

        if test.expected_reaction:
            checks.append(f"waiting for reaction {test.expected_reaction}")

        if test.validator is not None:
            checks.append("validator rejected event")

        if not checks:
            return "event did not satisfy an unknown condition"
        return ", ".join(checks)

    async def _send_test_result_message(self, result: SingleTestResult) -> None:
        """Send a polished and traceable outcome message for one test."""
        if self.test_channel is None:
            return

        cmd = result.sent_command
        trace = f"{result.test.cog}::{result.test.command}"
        duration = f"{result.duration_seconds:.1f}s"
        expectation = self._expectation_summary(result.test)

        if result.passed:
            response = self._truncate_text(result.response_preview or "[empty]")
            await self.test_channel.send(
                "\n".join(
                    [
                        f"✅ **PASS** `{cmd}` in `{duration}` | Cog: `{trace}`",
                        f"Expected: `{expectation}`",
                        f"Response: `{response}`",
                    ]
                )
            )
            return

        lines = [
            f"❌ **FAIL** `{cmd}` after `{duration}` | Cog: `{trace}`",
            f"Expected: `{expectation}`",
            f"Reason: {result.reason}",
        ]

        if result.mismatch_reasons:
            lines.append("Observed mismatches:")
            for mismatch in result.mismatch_reasons[:5]:
                lines.append(f"- {self._truncate_text(mismatch, limit=220)}")

        await self.test_channel.send("\n".join(lines))

    async def _send_final_report(self) -> None:
        """Publish a consolidated report with totals and failure traceability."""
        if self.test_channel is None:
            return

        total = self.results.passed + self.results.failed
        success_rate = (self.results.passed / total) * 100 if total else 0.0

        summary_lines = [
            "📋 **E2E Test Report**",
            f"Total: **{total}**",
            f"✅ Passed: **{self.results.passed}**",
            f"❌ Failed: **{self.results.failed}**",
            f"📈 Success rate: **{success_rate:.1f}%**",
        ]

        failures = [result for result in self.test_history if not result.passed]
        if failures:
            summary_lines.append("\n**Failure summary:**")
            for failure in failures:
                cmd = failure.sent_command
                summary_lines.append(
                    f"- `{failure.test.cog}::{failure.test.command}` / `{cmd}` ({failure.duration_seconds:.1f}s, {failure.attempts} msgs): {self._truncate_text(failure.reason, limit=180)}"
                )
        else:
            summary_lines.append("\nNo failures detected.")

        await self.test_channel.send("\n".join(summary_lines))

    async def _run_single_test(self, test: E2ETestCase) -> bool:
        """Run one command test from send-command to assertion.

        Listeners are registered BEFORE the command is sent to avoid the race
        condition where the target bot replies before ``wait_for`` is active.
        Both ``on_message`` and ``on_message_edit`` are watched so that bots
        that send a placeholder and later edit it are handled correctly.
        """
        if self.test_channel is None:
            raise RuntimeError("Test channel is not initialized.")

        queue: asyncio.Queue[ObservedEvent] = asyncio.Queue()

        async def _on_msg(message: discord.Message) -> None:
            if self._is_expected_response_author(message):
                queue.put_nowait(ObservedEvent(kind="message", message=message))

        async def _on_edit(_before: discord.Message, after: discord.Message) -> None:
            if self._is_expected_response_author(after):
                queue.put_nowait(ObservedEvent(kind="message", message=after))

        async def _on_reaction(
            reaction: discord.Reaction, user: discord.abc.User
        ) -> None:
            if self._is_expected_reaction_actor(
                reaction,
                user,
                self.test_channel,
                self.user,
                self.target_bot_id,
            ):
                queue.put_nowait(
                    ObservedEvent(
                        kind="reaction",
                        message=reaction.message,
                        emoji=str(reaction.emoji),
                        user_id=user.id,
                    )
                )

        self.add_listener(_on_msg, "on_message")
        self.add_listener(_on_edit, "on_message_edit")
        self.add_listener(_on_reaction, "on_reaction_add")

        rendered = test.send_text(self) if callable(test.send_text) else test.send_text
        command_text = _render_command_text(rendered)

        for setup_message in test.before_messages:
            await self.test_channel.send(setup_message)

        await self.test_channel.send(f"🧪 Running `{command_text}`: {test.description}")
        await self.test_channel.send(command_text)

        start = datetime.now()
        mismatch_reasons: list[str] = []
        attempts = 0

        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + test.timeout_seconds

            while True:
                timeout_left = deadline - loop.time()
                if timeout_left <= 0:
                    raise asyncio.TimeoutError

                candidate = await asyncio.wait_for(queue.get(), timeout=timeout_left)
                attempts += 1

                if event_matches_test(candidate, test):
                    response_preview = self._event_preview(candidate)
                    duration = (datetime.now() - start).total_seconds()
                    result = SingleTestResult(
                        test=test,
                        passed=True,
                        reason="matched expected criteria",
                        attempts=attempts,
                        duration_seconds=duration,
                        sent_command=command_text,
                        response_preview=response_preview,
                    )
                    self.test_history.append(result)
                    await self._send_test_result_message(result)
                    self.results.passed += 1
                    return True

                mismatch_reasons.append(
                    f"{self._event_preview(candidate)} -> "
                    f"{self._event_mismatch_reason(candidate, test)}"
                )

                if self.verbose:
                    logger.info(
                        "Mismatch for '%s': %s",
                        test.command,
                        mismatch_reasons[-1],
                    )

        except asyncio.TimeoutError:
            duration = (datetime.now() - start).total_seconds()
            attempts_text = f"{attempts} candidate response(s) seen"
            if attempts == 0:
                reason = (
                    f"timeout after {test.timeout_seconds:.0f}s with no response "
                    "from target bot"
                )
            else:
                reason = (
                    f"timeout after {test.timeout_seconds:.0f}s; no response matched "
                    f"expectation ({attempts_text})"
                )

            result = SingleTestResult(
                test=test,
                passed=False,
                reason=reason,
                attempts=attempts,
                duration_seconds=duration,
                sent_command=command_text,
                mismatch_reasons=mismatch_reasons,
            )
            self.test_history.append(result)
            await self._send_test_result_message(result)
            self.results.failed += 1
            return False

        finally:
            self.remove_listener(_on_msg, "on_message")
            self.remove_listener(_on_edit, "on_message_edit")
            self.remove_listener(_on_reaction, "on_reaction_add")

    async def on_message(self, message: discord.Message):
        # Ignore messages from ourselves
        if message.author == self.user:
            return

        if self.verbose:
            logger.info(f"Received message: {message.content} from {message.author}")

        if message.content.startswith(".start"):
            await self.start_tests(message)
        elif message.content.startswith(".status"):
            await self.status_command(message)
        elif message.content.startswith("."):
            await message.channel.send(
                "Unknown command. Use `.start` to run tests or `.status` to check results."
            )

    async def start_tests(self, message: discord.Message):
        """Command to start the E2E tests."""
        if self.running_tests:
            await message.channel.send(
                "E2E tests are already running. Please wait for them to finish."
            )
            return

        if message.guild is None:
            await message.channel.send("This command must be used in a server channel.")
            return

        await message.channel.send("Starting E2E tests...")

        if isinstance(message.channel, discord.TextChannel):
            self.test_channel = message.channel
        else:
            await message.channel.send(
                "This command must be used in a server text channel."
            )
            return

        self.running_tests = True
        self.results = TestStats()
        self.test_history = []
        for test in test_cases:
            await self._run_single_test(test)

        self.running_tests = False
        await self._send_final_report()

    async def status_command(self, message: discord.Message):
        """Utility method to send status updates to the test channel."""
        await message.channel.send(
            f"Is Running: {self.running_tests}, Passed: {self.results.passed}, Failed: {self.results.failed}"
        )


if __name__ == "__main__":
    tester_token = env.str("E2E_TESTER_BOT_TOKEN", "")
    if not tester_token:
        logger.error("E2E_TESTER_BOT_TOKEN is not set in .env")
        sys.exit(1)

    e2e_tester = E2ETester()
    e2e_tester.run(tester_token)
