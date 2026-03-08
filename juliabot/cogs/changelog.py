from discord.ext import commands

from ..client import Client
from ..collect_updates import UpdateCollector
from ..embeds.changelog import changelog_embed
from ..models import Server



class ChangelogCog(commands.Cog):
    """Changelog"""

    embed_title = ":newspaper: Changelog"

    def __init__(self, bot: Client) -> None:
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        servers = Server.get_servers_with_changelog_channel()
        for server in servers:
            guild = self.bot.get_guild(int(server.server_id))
            if not guild: continue

            last_hash = server.last_changelog_hash
            if last_hash:
                updates = UpdateCollector.get_commits_since_hash(last_hash)
            else:
                updates = UpdateCollector.get_last_n_commits(10)
            
            if not updates: continue
            
            channel = guild.get_channel(int(server.changelog_channel))
            if not channel: continue
            
            embed = changelog_embed(updates, self.bot.color)
            # mudar titulo para nova atualização
            embed.title = f":tada: Nova atualização"
            embed.description = f"Versão: {updates[0].hash} | {updates[0].date}"

            await channel.send(embed=embed)
            server.last_changelog_hash = updates[0].hash

        
    @commands.command(
        name="changelog",
        brief="Mostra as últimas atualizações do Bot.",
        description="Mostra as últimas atualizações do Bot, incluindo novas funcionalidades, correções de bugs e melhorias.",
        aliases=["updates", "novidades", "upd"]
    )
    async def changelog(self, ctx: commands.Context):
        updates = UpdateCollector.get_last_n_commits(10)
        if not updates:
            await ctx.send("Nenhuma atualização encontrada.")
            return
        
        embed = changelog_embed(updates, self.bot.color)
        await ctx.send(embed=embed)


    @commands.guild_only()
    @commands.command(
        name="set_changelog_channel",
        brief="Define o canal para enviar o changelog automaticamente.",
        description="Define o canal para enviar o changelog automaticamente sempre que houver uma nova atualização do Bot. Use `!remove_changelog_channel` para desativar.",
        aliases=["scc", "set_changelog", "definir_canal_changelog"]
    )
    async def set_changelog_channel(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        channel_id = ctx.channel.id

        server = Server.get_or_create(str(guild_id))
        server.changelog_channel = str(channel_id)
        server.update()

        await ctx.send(f"Canal de changelog definido para {ctx.channel.mention}.")

    @commands.guild_only()
    @commands.command(
        name="remove_changelog_channel",
        brief="Remove o canal de changelog automático.",
        description="Remove o canal de changelog automático, desativando o envio de atualizações do Bot. Use `!set_changelog_channel` para definir um novo canal.",
        aliases=["rcc", "remove_changelog", "remover_canal_changelog"]
    )
    async def remove_changelog_channel(self, ctx: commands.Context):
        guild_id = ctx.guild.id

        server = Server.get_or_create(str(guild_id))
        server.changelog_channel = None
        server.update()

        await ctx.send("Canal de changelog automático removido.")

    @commands.guild_only()
    @commands.command(
        name="changelog_channel",
        brief="Mostra o canal de changelog automático.",
        description="Mostra o canal de changelog automático, onde as atualizações do Bot são enviadas. Use `!set_changelog_channel` para definir ou `!remove_changelog_channel` para remover.",
        aliases=["cc", "changelog_canal", "canal_changelog"]
    )
    async def changelog_channel(self, ctx: commands.Context):
        guild_id = ctx.guild.id

        server = Server.get_or_create(str(guild_id))
        if server.changelog_channel:
            channel = ctx.guild.get_channel(int(server.changelog_channel))
            if channel:
                await ctx.send(f"O canal de changelog automático é {channel.mention}.")
            else:
                await ctx.send("O canal de changelog automático definido não existe mais. Use `!remove_changelog_channel` para limpar a configuração.")
        else:
            await ctx.send("Nenhum canal de changelog automático definido. Use `!set_changelog_channel` para definir um.")
        

async def setup(bot: Client) -> None:
    await bot.add_cog(ChangelogCog(bot))
