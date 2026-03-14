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
from dataclasses import dataclass
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

            print(
                f"Checking embed text:\n{embed_text}\nAgainst pattern: {test.expected_embed.pattern}"
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

    async def _run_single_test(self, test: E2ETestCase) -> bool:
        """Run one command test from send-command to assertion."""
        if self.test_channel is None:
            raise RuntimeError("Test channel is not initialized.")

        await self.test_channel.send(f"Running test: {test.description}")
        await self.test_channel.send(f"{prefix}{test.command}")

        def check(message: discord.Message) -> bool:
            return self._is_expected_response_author(message) and message_matches_test(
                message, test
            )

        try:
            response = await self.wait_for(
                "message", check=check, timeout=test.timeout_seconds
            )
            response_preview = self._format_response_preview(response)
            await self.test_channel.send(
                f"✅ Test passed! Received expected response: {response_preview}"
            )
            self.results.passed += 1
            return True
        except asyncio.TimeoutError:
            await self.test_channel.send(
                f"❌ Test failed! No matching response received in {test.timeout_seconds:.0f}s."
            )
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
        for test in test_cases:
            await self._run_single_test(test)

        self.running_tests = False
        await self.test_channel.send("E2E tests completed!")
        await self.test_channel.send(
            f"Results: {self.results.passed} passed, {self.results.failed} failed."
        )

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
