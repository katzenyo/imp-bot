import datetime
import logging
import os

import aiosqlite
import discord
from discord.ext import commands
from dotenv import load_dotenv

import twitch_auth

load_dotenv(override=True)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

discord_handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')

_app_handler = logging.FileHandler(filename='impbot.log', encoding='utf-8', mode='a')
_app_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[_app_handler])
logging.getLogger('discord').propagate = False

log = logging.getLogger(__name__)

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from the environment. Check your .env file.")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True


class ImpBot(commands.Bot):
    async def setup_hook(self) -> None:
        cogs_list = [
            'slash',
            'events',
            'birthdays',
            'letterboxd',
            'starboard',
            'lpc',
            'poll',
            'twitch'
        ]

        for cog in cogs_list:
            try:
                await self.load_extension(cog)
                print(f'{cog} successfully loaded!')
                log.info(f'{cog} successfully loaded!')
            except Exception as e:
                print(f'{cog} loading failed: {e}')
                log.error(f'{cog} loading failed: {e}')



bot = ImpBot(
    command_prefix='!',
    description='IMP BOT 9000 COMMAND INDEX',
    intents=intents
    )

##############################################################################
############################## EVENTS SECTION ################################
##############################################################################

@bot.event
async def on_ready():
    print('CBot is logged in as {0.user}'.format(bot))
    log.info('CBot is logged in as {0.user}'.format(bot))
    await bot.change_presence(activity=discord.Game(f"Danny Simulator {datetime.date.today().year+1}"))

##############################################################################
############################## COMMANDS SECTION ##############################
##############################################################################

@bot.command()
@commands.is_owner()
async def sync(ctx: commands.Context) -> None:
    """Syncs commands globally"""
    synced = await ctx.bot.tree.sync()
    await ctx.send(f'Synced {len(synced)} commands globally')

@bot.command()
@commands.is_owner()
async def refresh_twitch(ctx: commands.Context) -> None:
    """Manually refreshes the Twitch API token"""
    async with aiosqlite.connect('impbot.db') as db:
        try:
            await twitch_auth.force_refresh(db)
            await ctx.send('Twitch token refreshed successfully.')
        except RuntimeError as e:
            await ctx.send(f'Refresh failed: {e}')

@bot.command(description='Returns some basic stats about the user.')
async def whois(ctx: commands.Context, *, member: discord.Member):
    info = '{0} joined on {0.joined_at} and has {1} roles.'
    await ctx.send(info.format(member, len(member.roles)))

# @bot.command()
# @commands.is_owner()
# async def test_notification(ctx: commands.Context, twitch_login: str) -> None:
#     cog = bot.cogs.get('TwitchCog')
#     payload = {
#         'event': {
#             'broadcaster_user_id': '10386664',
#             'broadcaster_user_login': twitch_login,
#         }
#     }
#     await cog._handle_notification(payload)
#     await ctx.send('Notification sent.')


bot.run(f"{DISCORD_TOKEN}", log_handler=discord_handler, log_level=logging.DEBUG)
