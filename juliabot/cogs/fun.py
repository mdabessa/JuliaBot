from discord.ext import commands
from discord import User
from random import randint


from ..scripts import Script


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
    
    @staticmethod
    @Script.function(name='duel', events=['on_reaction_add'], limit_by_name=2)
    async def _duel(cache: dict, **kwargs): 
        if cache["status"] == "created":
            msg = kwargs['message']
            vs = msg.mentions[0]

            m = await msg.channel.send(
                f"{msg.author.mention} desafia {vs.mention} para um duelo!"
            )

            await m.add_reaction("👍")
            await m.add_reaction("👎")

            cache["message"] = m
            cache["author"] = msg.author
            cache["vs"] = vs
            cache["status"] = "started"
        else:
            m = cache["message"]
            author = cache["author"]
            vs = cache["vs"]

            user = kwargs['user']
            emoji = kwargs['emoji']
            if emoji == "👍" and vs == user:
                if randint(0, 1) == 1:
                    await m.channel.send(
                        f"{vs.mention} aceitou o duelo e venceu! \n{author.mention} perdeu o duelo! :sob:"
                    )

                else:
                    await m.channel.send(
                        f"{vs.mention} aceitou o duelo e perdeu! \n{author.mention} ganhou o duelo! :sunglasses:"
                    )
                cache["status"] = 0

            elif emoji == "👎" and user in [vs, author]:
                await m.channel.send(f"{user.mention} recusou o duelo!")

                cache["status"] = 0


    @commands.command(
        name='duel',
        brief='Desafie alguem para uma duelo!',
        aliases=['desafiar']
        )
    async def duel(self, ctx: commands.Context, *, user: User):
        scr = Script(f'duel_{ctx.guild.id}', 'duel')
        await scr.execute(message=ctx.message)



def setup(bot: commands.Bot):
    bot.add_cog(Fun(bot))

