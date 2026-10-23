"""Fun and game commands cog.

Provides entertainment commands like duels, dice rolls, and random options.
"""

import time
from random import randint, shuffle
from typing import Optional

from discord import User
from discord.ext import commands

from ..client import Client
from ..sessions import (
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)
from ..sessions.patterns import PromptChoice, PromptSession

DUEL = "fun.duel"


class DuelPrompt(PromptSession):
    """Ask the challenged user to accept or decline a duel."""

    choices = (
        (
            "accept",
            PromptChoice("Aceitar", emoji="👍", style="success", owner_only=False),
        ),
        (
            "decline",
            PromptChoice("Recusar", emoji="👎", style="danger", owner_only=False),
        ),
    )

    def _int_payload(self, key: str) -> int:
        """Read an integer id from the typed payload boundary."""
        value = self._payload.get(key, 0)
        return int(value) if isinstance(value, (int, float)) else 0

    @property
    def author_id(self) -> int:
        """Return the challenger id."""
        return self._int_payload("author_id")

    @property
    def vs_id(self) -> int:
        """Return the challenged user id."""
        return self._int_payload("vs_id")

    async def render_prompt(self) -> str:
        """Announce the challenge with both participants mentioned."""
        return f"<@{self.author_id}> desafia <@{self.vs_id}> para um duelo!"

    def can_handle(self, choice: str, event: InteractionEvent) -> bool:
        """Only the challenged user accepts; either participant may decline."""
        if choice == "accept":
            return event.user_id == self.vs_id
        if choice == "decline":
            return event.user_id in (self.author_id, self.vs_id)
        return False

    async def on_choice(self, choice: str, event: InteractionEvent) -> None:
        """Announce the duel result."""
        if self._message is None:
            return
        channel = self._message.channel
        if choice == "accept":
            if randint(0, 1) == 1:
                await channel.send(
                    f"<@{self.vs_id}> aceitou o duelo e venceu! \n"
                    f"<@{self.author_id}> perdeu o duelo! :sob:"
                )
            else:
                await channel.send(
                    f"<@{self.vs_id}> aceitou o duelo e perdeu! \n"
                    f"<@{self.author_id}> ganhou o duelo! :sunglasses:"
                )
        elif choice == "decline":
            await channel.send(f"<@{event.user_id}> recusou o duelo!")


class FunCog(commands.Cog, name="fun"):
    """Entertainment and game commands.

    Provides interactive games like duels and dice rolls with discord.py
    button-based UI.
    """

    embed_title = ":game_die:Diversão."

    def __init__(self, bot: Client) -> None:
        self.bot = bot
        if not hasattr(bot, "sessions"):
            bot.sessions = SessionManager(Registry())
        if bot.sessions.registry.get(DUEL) is None:
            bot.sessions.registry.register(
                Registration(
                    name=DUEL,
                    session_class=DuelPrompt,
                    trigger=TriggerType.COMPONENT,
                    scope=Scope.GUILD,
                    timeout=60,
                    max_per_scope=2,
                )
            )

    @commands.command(
        name="duel", brief="Desafie alguem para uma duelo!", aliases=["desafiar"]
    )
    async def duel(self, ctx: commands.Context, *, user: User):
        event = InteractionEvent(
            transport=TriggerType.COMPONENT,
            key=str(ctx.message.id),
            user_id=ctx.author.id,
            guild_id=getattr(ctx.guild, "id", None),
            channel_id=ctx.channel.id,
            message_id=ctx.message.id,
            raw=ctx,
        )
        await self.bot.sessions.start(
            DUEL,
            event,
            payload={"author_id": ctx.author.id, "vs_id": user.id},
        )

    @commands.command(name="dice", brief="Role um dado.", aliases=["dado", "d", "roll"])
    async def dice(self, ctx: commands.Context, *, args: Optional[str] = None):
        view_rolls = 3
        if args is None:
            args = "6"

        try:
            sides = int(args)
            if sides < 2:
                await ctx.send("O dado precisa ter mais de 1 lado!")
                return

            results = list(range(1, sides + 1))
            shuffle(results)
            if sides <= view_rolls:
                for i in range(0, view_rolls - len(results)):
                    results.append(randint(1, sides))

        except ValueError:
            if ";" in args:
                options = args.split(";")
            elif "," in args:
                options = args.split(",")
            else:
                options = args.split(" ")

            results = options
            shuffle(results)
            if len(options) <= view_rolls:
                for i in range(0, view_rolls - len(options)):
                    results.append(options[randint(0, len(options) - 1)])

        msg = await ctx.send(f":game_die: {results[0]} :game_die:")
        time
        for i in range(1, view_rolls):
            time.sleep(0.5)
            await msg.edit(content=f":game_die: {results[i]} :game_die:")

        time.sleep(0.5)
        await msg.edit(content=f"Resultado: {results[-1]} :game_die:")


async def setup(bot: Client):
    await bot.add_cog(FunCog(bot))
