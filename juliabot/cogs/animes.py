from discord import Embed
from discord.ext import commands
import jikanpy as jk



class Anime(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> dict | None:
        msg = await ctx.send(f'Procurando anime: `{argument}`...')
        jikan = jk.Jikan()
        try:
            anime = jikan.search('anime', argument)['results'][0]
        except:
            anime = None
        
        await msg.delete()

        return anime


class Character(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> dict | None:
        msg = await ctx.send(f'Procurando char: `{argument}`...')
        jikan = jk.Jikan()
        try:
            char = jikan.search('character', argument)['results'][0]
        except:
            char = None
        
        await msg.delete()

        return char


class Animes(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.command(
        name='anime_info',
        brief='Retornar informações sobre um anime.',
        aliases=['anime', 'ai']
    )
    async def anime_info(self, ctx: commands.Context, *, anime: Anime):
        if anime:
            emb = Embed(
                title=anime["title"], description=anime["synopsis"], color=self.bot.color
            )
            emb.set_thumbnail(url=anime["image_url"])

            emb.add_field(name="Episódios:", value=anime["episodes"], inline=False)
            emb.add_field(name="Score (MyAnimeList):", value=anime["score"], inline=False)
            emb.add_field(name="Tipo:", value=anime["type"], inline=False)
            emb.add_field(
                name="Lançando:", value="Sim" if anime["airing"] else "Não", inline=False
            )
            emb.add_field(
                name="Link:", value=f'[MyAnimeList]({anime["url"]})', inline=False
            )

            await ctx.send(embed=emb)

        else:
            await ctx.send('Não consegui achar nenhum anime com esse nome. 🙁')


    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.command(
        name='char_info',
        brief='Retornar informações sobre um personagem.',
        aliases=['char', 'ci', 'personagem']
    )
    async def char_info(self, ctx: commands.Context, *, char: Character):
        if char:
            emb = Embed(
                title=char["name"],
                description=" ,".join(f"`{x}`" for x in char["alternative_names"]),
                color=self.bot.color,
            )
            emb.set_image(url=char["image_url"])

            _animes = ""
            animes = ""
            for ani in char["anime"]:
                _animes += f'[{ani["name"]}]({ani["url"]}), '
                if len(_animes) > 500:
                    break
                else:
                    animes = _animes

            if len(animes) > 0:
                animes = animes[:-2]
                emb.add_field(name="Animes:", value=animes, inline=False)

            _mangas = ""
            mangas = ""
            for manga in char["manga"]:
                _mangas += f'[{manga["name"]}]({manga["url"]}), '
                if len(_mangas) > 500:
                    break
                else:
                    mangas = _mangas

            if len(mangas) > 0:
                mangas = mangas[:-2]
                emb.add_field(name="Mangas:", value=mangas, inline=False)

            await ctx.send(embed=emb)

        else:
            await ctx.send('Não consegui achar nenhum personagem com esse nome. 🙁')



def setup(bot: commands.Bot):
    bot.add_cog(Animes(bot))
