from discord.ext import commands
from deep_translator import GoogleTranslator


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


def setup(bot: commands.Bot):
    bot.add_cog(Utilities(bot))
