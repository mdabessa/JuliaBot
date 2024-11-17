import requests

from discord.ext import commands, tasks

from ..models import TwitchNotifier


class Twitch(commands.Cog):
    """Twitch"""

    embed_title = ":tv: Twitch"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.check_streamers.start()


    @staticmethod
    def get_streamer_url(streamer: str) -> str:
        return f"https://www.twitch.tv/{streamer}"
    
    @staticmethod
    def is_streamer_online(streamer: str) -> bool:
        url = Twitch.get_streamer_url(streamer)
        response = requests.get(url)
        return response.status_code == 200 and 'isLiveBroadcast' in response.text
    

    @commands.command(
        name="stream",
        brief="Verifica se um streamer está online.",
        description="Verifica se dado streamer está online na Twitch.",
        aliases=["str", "streamer"],
    )
    async def stream(self, ctx: commands.Context, streamer: str):
        status = Twitch.is_streamer_online(streamer)
        status = "online" if status else "offline"

        await ctx.send(f"`{streamer}` está {status}.")

    @commands.command(
        name="add_streamer",
        brief="Adiciona um streamer para ser notificado.",
        description="Adiciona um streamer para ser notificado quando estiver online.",
        aliases=["add_str"],
    )
    async def add_streamer(self, ctx: commands.Context, streamer: str):
        if TwitchNotifier.get(streamer, str(ctx.channel.id)) is not None:
            await ctx.send(f"O canal atual já está recebendo notificações de `{streamer}`.")
            return

        TwitchNotifier(streamer, str(ctx.channel.id))
        await ctx.send(f"`{streamer}` foi adicionado para notificação.")

    @commands.command(
        name="remove_streamer",
        brief="Remove um streamer da lista de notificação.",
        description="Remove um streamer da lista de notificação.",
        aliases=["remove_str"],
    )
    async def remove_streamer(self, ctx: commands.Context, streamer: str):
        notifier = TwitchNotifier.get(streamer, str(ctx.channel.id))

        if notifier is None:
            await ctx.send(f"`{streamer}` não está na lista de notificação.")
            return

        notifier.delete()
        await ctx.send(f"`{streamer}` foi removido da lista de notificação deste canal.")

    
    @commands.command(
        name="list_streamers",
        brief="Lista os streamers que estão sendo notificados.",
        description="Lista os streamers que estão sendo notificados.",
        aliases=["list_str", "list_streamer"],
    )
    async def list_streamers(self, ctx: commands.Context):
        streamers = TwitchNotifier.get_by_channel(str(ctx.channel.id))

        if not streamers:
            await ctx.send("Nenhum streamer está sendo notificado neste canal.")
            return

        streamers = [f"`{streamer.streamer_id}`" for streamer in streamers]
        await ctx.send(f"Streamers notificados neste canal: {', '.join(streamers)}")


    # Debugging purposes
    @commands.command(
        name="reset_notifications",
        brief="Reseta as notificações de streamers.",
        description="Reseta as notificações de streamers, notificando todos os streamers online novamente.",
    )
    async def reset_notifications(self, ctx: commands.Context):
        TwitchNotifier.reset()
        await ctx.send("As notificações de streamers foram resetadas.")


    @tasks.loop(minutes=5)
    async def check_streamers(self):
        cache = {}
        for notifier in TwitchNotifier.get_all():
            if notifier.streamer_id not in cache:
                cache[notifier.streamer_id] = Twitch.is_streamer_online(notifier.streamer_id)

            if cache[notifier.streamer_id] and not notifier.notified:
                channel = self.bot.get_channel(int(notifier.channel_id))
                await channel.send(
                    f"{notifier.streamer_id} está online! Assista em {Twitch.get_streamer_url(notifier.streamer_id)}."
                )
                
                notifier.notified = True
                notifier.update()
            
            else:
                # reset notification if streamer goes offline
                notifier.notified = False
                notifier.update()


def setup(bot: commands.Bot):
    bot.add_cog(Twitch(bot))
