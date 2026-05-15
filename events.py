import discord
from discord.ext import commands


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = member.guild.system_channel
        if channel is not None:
            await channel.send(f'Welcome to {member.display_name} to {member.guild.name}!')

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = member.guild.system_channel
        if channel is not None:
            await channel.send(f'{member.display_name} has abandoned the cause and left {member.guild.name}!')


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
