import os

from deep_translator import GoogleTranslator
from discord import File
from discord.ext import commands, tasks

from ..converters import Date


class Utilities(commands.Cog):
    """Utilities"""

    embed_title = ":paperclip: Utilities"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(
        name="translate",
        brief="Traduz um texto para a língua desejada.",
        description="Detecta automaticamente a língua do texto e traduz para a língua desejada usando o Google Translate.",
        aliases=["traduzir", "tr"],
    )
    async def translate(self, ctx: commands.Context, *, args: str) -> None:
        try:
            lang = args.split(" ")[0]
            if GoogleTranslator().is_language_supported(lang):
                text = " ".join(args.split(" ")[1:])

            else:
                text = args
                lang = "pt"

            if not text:
                await ctx.send("Você precisa escrever um texto para ser traduzido.")
                return

            if len(text) > 2000:
                await ctx.send("O texto não pode ter mais de 2000 caracteres.")
                return

            translated = GoogleTranslator(source="auto", target=lang).translate(text)
            await ctx.send(translated)

        except Exception as e:
            await ctx.send(f"Ocorreu um erro ao traduzir o texto: {e}")

    @commands.command(
        name="channel_history",
        brief="Mostra o histórico de mensagens de um canal.",
        description="Mostra as últimas mensagens de um canal.",
        aliases=["ch"],
    )
    async def channel_history(
        self,
        ctx: commands.Context,
        channel: commands.TextChannelConverter = None,
        start: Date = None,
        end: Date = None,
    ) -> None:

        channel = channel or ctx.channel

        msg = await ctx.send(f"Buscando histórico de mensagens de {channel.mention}...")

        fp = "channel_history.txt"
        c = 0
        with open(fp, "w", encoding="utf-8") as f:
            async for message in channel.history(
                limit=None, oldest_first=True, after=start, before=end
            ):
                text = f"{message.created_at} {message.guild.name}[{message.channel.name}] {message.author}: {message.content}\n"
                f.write(text)
                c += 1

                if c % 10000 == 0:
                    await msg.edit(
                        content=f"Buscando histórico de mensagens de {channel.mention}... ({c} mensagens) | em [{message.created_at}]"
                    )

        await msg.delete()
        await ctx.send("Histórico de mensagens:", file=File(fp))
        os.remove(fp)


def setup(bot: commands.Bot):
    bot.add_cog(Utilities(bot))
