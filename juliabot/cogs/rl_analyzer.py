from asyncio import sleep
from typing import Optional

from discord import Embed, File
from discord.ext import commands

from ..models import RocketLeague
from ..rl_analyzer import RANKS, query_replays, replay_analyzer
from ..scripts import Script


class RLAnalyzer(commands.Cog, name="rlanalyzer"):
    """Categoria relacionada a comandos do Rocket League Analyzer."""

    embed_title = ":rocket:RL Analyzer."

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def embed_player(player: dict, color) -> Embed:
        tags = ""
        for tag in player["predict"]["tags"]:
            tags += f'[`{tag["name"]}`](https://www.google.com "{tag["description"]}") '

        tags = tags if tags else "** **"

        desc = f'Team {player["team"].capitalize()}'
        embed = Embed(title=player["name"], description=desc, color=color)

        embed.add_field(
            name="Rank:",
            value=RANKS[player["tier"] - 1].capitalize().replace("-", " "),
            inline=False,
        )
        embed.add_field(
            name="Analyzer Rank:",
            value=RANKS[player["predict"]["tier"] - 1].capitalize().replace("-", " "),
            inline=False,
        )
        embed.add_field(
            name="Score:", value=player["stats"]["core"]["score"], inline=True
        )
        embed.add_field(
            name="Goals:", value=player["stats"]["core"]["goals"], inline=True
        )
        embed.add_field(
            name="Saves:", value=player["stats"]["core"]["saves"], inline=True
        )
        embed.add_field(name="Tags:", value=tags, inline=False)

        return embed

    @staticmethod
    @Script.function(name="replay_analyzer", events=["on_reaction_add"])
    async def _replay_analyzer(cache: dict, **kwargs):
        if cache["status"] == "created":
            ctx = kwargs["ctx"]
            replay = kwargs["replay"]

            players = []
            for team in ["orange", "blue"]:
                for player in replay[team]["players"]:
                    tier = (
                        replay["min_rank"]["tier"]
                        if "min_rank" in replay
                        else replay["max_rank"]["tier"]
                    )

                    player["team"] = team
                    player["tier"] = tier
                    players.append(player)

            player = players[0]

            emb = RLAnalyzer.embed_player(player, ctx.bot.color)
            emb.set_thumbnail(url=f"attachment://tier_{player['predict']['tier']}.png")
            file = File(
                f'./juliabot/images/rl_logos/{player["predict"]["tier"]}.png',
                filename=f'tier_{player["predict"]["tier"]}.png',
            )

            message = await ctx.send(file=file, embed=emb)

            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")

            cache["index"] = 0
            cache["status"] = "started"
            cache["message"] = message
            cache["players"] = players
            cache["replay"] = replay
            cache["ctx"] = ctx

        else:
            emoji = kwargs["emoji"]

            ctx = cache["ctx"]
            message = cache["message"]
            players = cache["players"]
            index = cache["index"]

            if emoji == "➡️":
                index += 1
                if index >= len(players):
                    index = 0

            if emoji == "⬅️":
                index -= 1
                if index < 0:
                    index = len(players) - 1

            cache["index"] = index

            await message.delete()

            player = players[index]
            emb = RLAnalyzer.embed_player(player, ctx.bot.color)
            emb.set_thumbnail(url=f"attachment://tier_{player['predict']['tier']}.png")
            file = File(
                f'./juliabot/images/rl_logos/{player["predict"]["tier"]}.png',
                filename=f'tier_{player["predict"]["tier"]}.png',
            )

            message = await ctx.send(file=file, embed=emb)

            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")

            cache["message"] = message

    @commands.dm_only()
    @commands.command(
        brief="Define o token para usar os comandos da categoria RL Analyzer.",
        help="Define o token de autorização para poder interagir com a API ballchasing.com.",
        aliases=["rlt"],
    )
    async def rl_token(self, ctx: commands.Context, token: str):
        user = RocketLeague.get(str(ctx.author.id))

        if user is None:
            user = RocketLeague(str(ctx.author.id))

        user.set_ballchasing_token(token)

        await ctx.send("Seu token foi atualizado!")

    @commands.command(
        brief="Analize um replay de Rocket League.",
        help="Analiza o replay de uma partida de Rocket League postado no ballchasing.com.",
        aliases=["ra"],
    )
    async def replay_analyzer(self, ctx: commands.Context, replay_id: str):
        user = RocketLeague.get(str(ctx.author.id))

        if (user is None) or (user.ballchasing_token is None):
            await ctx.send(
                "Você precisa configurar um token de acesso com o comando `rl_token`. O token pode ser obtido em `ballchasing.com` gerando uma API Key."
            )
            return

        msg = await ctx.send("Pesquisando replay...")
        response = replay_analyzer(replay_id, user.ballchasing_token)
        await msg.delete()

        if response.status_code == 401:
            await ctx.send(
                "O seu token está errado. Você precisa configurar um token de acesso com o comando `rl_token`. O token pode ser obtido em `ballchasing.com` gerando uma API Key."
            )
            return

        if response.status_code != 200:
            await ctx.send(f"Um erro ocorreu com a API.\n{response.text}")
            return

        replay = response.json()
        scr = Script(f"replay_analyzer{ctx.guild.id}", "replay_analyzer", time_out=300)
        await scr.execute(ctx=ctx, replay=replay)

    @commands.command(
        brief="Analize o ultimo replay de um player de Rocket League.",
        help="Analiza o ultimo replay de um player de Rocket League postado no ballchasing.com.",
        aliases=["ana"],
    )
    async def analyzer_last(self, ctx: commands.Context, player: Optional[str] = None):
        user = RocketLeague.get(str(ctx.author.id))

        if (user is None) or (user.ballchasing_token is None):
            await ctx.send(
                "Você precisa configurar um token de acesso com o comando `rl_token`. O token pode ser obtido em `ballchasing.com` gerando uma API Key."
            )
            return

        player = str(ctx.author.name) if player is None else player

        msg = await ctx.send(f"Pesquisando ultimo replay de `{player}`...")

        replays = query_replays(
            query={"player-name": player}, token=user.ballchasing_token
        ).json()["list"]

        await sleep(2)

        if len(replays) == 0:
            await ctx.send(f"Não foi encontrado nenhum replay de `{player}`.")
            return

        replay = replays[0]

        response = replay_analyzer(replay["id"], user.ballchasing_token)
        await msg.delete()

        if response.status_code == 401:
            await ctx.send(
                "O seu token está errado. Você precisa configurar um token de acesso com o comando `rl_token`. O token pode ser obtido em `ballchasing.com` gerando uma API Key."
            )
            return

        if response.status_code != 200:
            await ctx.send(f"Um erro ocorreu com a API.\n{response.text}")
            return

        replay = response.json()
        scr = Script(f"replay_analyzer{ctx.guild.id}", "replay_analyzer", time_out=300)
        await scr.execute(ctx=ctx, replay=replay)


def setup(bot: commands.Bot):
    bot.add_cog(RLAnalyzer(bot))
