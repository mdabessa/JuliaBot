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


prefix = "!"


@dataclass(frozen=True)
class E2ETestCase:
    """Declarative structure for an end-to-end command test."""

    command: str
    description: str
    expected_response: Optional[Pattern[str]] = None
    expected_embed: Optional[Pattern[str]] = None
    timeout_seconds: float = 10.0
    validator: Optional[Callable[[discord.Message], bool]] = None


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
    response_preview: Optional[str] = None
    mismatch_reasons: list[str] = field(default_factory=list)


test_cases = [
    E2ETestCase(
        command="ping",
        description="Test the ping command for a valid response.",
        expected_response=re.compile(r"ping", re.IGNORECASE),
    ),
    E2ETestCase(
        command="help",
        description="Test the help command for a valid response.",
        expected_embed=re.compile(r"lista de comandos", re.IGNORECASE),
    ),
]


def message_matches_test(
    message: discord.Message,
    test: E2ETestCase,
) -> bool:
    """Return True when a message satisfies the expected test response.

    Supports plain text checks (`expected_response`) and embed checks
    (`expected_embed`) because some commands (e.g. help) answer with embeds.
    """
    if test.expected_response and test.expected_response.search(message.content or ""):
        return True

    if test.expected_embed and message.embeds:
        for embed in message.embeds:
            parts = [
                embed.title or "",
                embed.description or "",
            ]
            parts.extend(field.name or "" for field in embed.fields)
            parts.extend(field.value or "" for field in embed.fields)
            embed_text = "\n".join(parts)

            logger.debug(
                "Checking embed text for '%s': %s | pattern=%s",
                test.command,
                embed_text,
                test.expected_embed.pattern,
            )
            if test.expected_embed.search(embed_text):
                return True

    if test.validator is not None:
        result = test.validator(message)
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
    def _format_response_preview(message: discord.Message) -> str:
        """Create a compact human-readable response summary for test logs."""
        if message.content:
            return message.content

        if message.embeds:
            first_embed = message.embeds[0]
            title = first_embed.title or "(no title)"
            description = first_embed.description or "(no description)"
            return f"[embed] {title} | {description}"

        return "[empty message]"

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
        if test.validator is not None:
            parts.append("custom validator")

        if not parts:
            return "no expectation defined"
        return " + ".join(parts)

    def _message_mismatch_reason(
        self, message: discord.Message, test: E2ETestCase
    ) -> str:
        """Explain why a candidate message did not satisfy the test."""
        checks = []

        if test.expected_response:
            if test.expected_response.search(message.content or ""):
                checks.append("text matched")
            else:
                checks.append("text did not match")

        if test.expected_embed:
            if not message.embeds:
                checks.append("embed missing")
            else:
                matched_embed = False
                for embed in message.embeds:
                    parts = [embed.title or "", embed.description or ""]
                    parts.extend(field.name or "" for field in embed.fields)
                    parts.extend(field.value or "" for field in embed.fields)
                    embed_text = "\n".join(parts)
                    if test.expected_embed.search(embed_text):
                        matched_embed = True
                        break
                checks.append(
                    "embed matched" if matched_embed else "embed did not match"
                )

        if test.validator is not None:
            checks.append("validator rejected message")

        if not checks:
            return "message did not satisfy an unknown condition"
        return ", ".join(checks)

    async def _send_test_result_message(self, result: SingleTestResult) -> None:
        """Send a polished and traceable outcome message for one test."""
        if self.test_channel is None:
            return

        cmd = f"{prefix}{result.test.command}"
        duration = f"{result.duration_seconds:.1f}s"
        expectation = self._expectation_summary(result.test)

        if result.passed:
            response = self._truncate_text(result.response_preview or "[empty]")
            await self.test_channel.send(
                "\n".join(
                    [
                        f"✅ **PASS** `{cmd}` in `{duration}`",
                        f"Expected: `{expectation}`",
                        f"Response: `{response}`",
                    ]
                )
            )
            return

        lines = [
            f"❌ **FAIL** `{cmd}` after `{duration}`",
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
                cmd = f"{prefix}{failure.test.command}"
                summary_lines.append(
                    f"- `{cmd}` ({failure.duration_seconds:.1f}s, {failure.attempts} msgs): {self._truncate_text(failure.reason, limit=180)}"
                )
        else:
            summary_lines.append("\nNo failures detected.")

        await self.test_channel.send("\n".join(summary_lines))

    async def _run_single_test(self, test: E2ETestCase) -> bool:
        """Run one command test from send-command to assertion."""
        if self.test_channel is None:
            raise RuntimeError("Test channel is not initialized.")

        await self.test_channel.send(
            f"🧪 Running `{prefix}{test.command}`: {test.description}"
        )
        await self.test_channel.send(f"{prefix}{test.command}")

        start = datetime.now()
        mismatch_reasons: list[str] = []
        attempts = 0

        def author_check(message: discord.Message) -> bool:
            return self._is_expected_response_author(message)

        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + test.timeout_seconds

            while True:
                timeout_left = deadline - loop.time()
                if timeout_left <= 0:
                    raise asyncio.TimeoutError

                candidate = await self.wait_for(
                    "message", check=author_check, timeout=timeout_left
                )
                attempts += 1

                if message_matches_test(candidate, test):
                    response_preview = self._format_response_preview(candidate)
                    duration = (datetime.now() - start).total_seconds()
                    result = SingleTestResult(
                        test=test,
                        passed=True,
                        reason="matched expected criteria",
                        attempts=attempts,
                        duration_seconds=duration,
                        response_preview=response_preview,
                    )
                    self.test_history.append(result)
                    await self._send_test_result_message(result)
                    self.results.passed += 1
                    return True

                mismatch_reasons.append(
                    f"{self._format_response_preview(candidate)} -> {self._message_mismatch_reason(candidate, test)}"
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
                reason = f"timeout after {test.timeout_seconds:.0f}s with no response from target bot"
            else:
                reason = (
                    f"timeout after {test.timeout_seconds:.0f}s; no response matched expectation "
                    f"({attempts_text})"
                )

            result = SingleTestResult(
                test=test,
                passed=False,
                reason=reason,
                attempts=attempts,
                duration_seconds=duration,
                mismatch_reasons=mismatch_reasons,
            )
            self.test_history.append(result)
            await self._send_test_result_message(result)
            self.results.failed += 1
            return False

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
