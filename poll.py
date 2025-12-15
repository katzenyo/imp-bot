import discord
from discord.ext import commands

class Poll(commands.Cog):
    def __init__(self, bot) -> None:
        super().__init__()
        self.bot = bot

    @commands.command()
    async def poll(self, ctx):
        await ctx.send('This will send something')