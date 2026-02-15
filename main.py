import logging
import json
import os
import datetime
from datetime import date
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

# loading API tokens as environment variables
load_dotenv()
DISCORD_TOKEN=os.getenv("DISCORD_TOKEN")
TWITCH_ACCESS_TOKEN=os.getenv("TWITCH_ACCESS_TOKEN")
TWITCH_CLIENT_ID=os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET=os.getenv("TWITCH_CLIENT_SECRET")

#logging.basicConfig(level=logging.INFO)
handler = logging.FileHandler(
    filename='discord.log',
    encoding='utf-8',
    mode='w'
    )

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True

bot = commands.Bot(
    command_prefix='!',
    description='CBOT 9000 COMMAND INDEX',
    intents=intents
    )

##############################################################################
############################## EVENTS SECTION ################################
##############################################################################

@bot.event
async def on_ready():
    print('CBot is logged in as {0.user}'.format(bot))
    await bot.change_presence(activity=discord.Game(f"Danny Simulator {date.today().year+1}"))

async def setup_hook():
    cogs_list = [
        'slash',
        'events',
        'birthdays',
        'letterboxd'
    ]

    for cog in cogs_list:
        try:
            await bot.load_extension(cog)
            print(f'{cog} successfully loaded!')
        except Exception as e:
            print(f'{cog} loading failed: {e}')

    twitch_headers = {'Authorization': f'Bearer {TWITCH_ACCESS_TOKEN}'}
    async with aiohttp.ClientSession(headers=twitch_headers) as session:
        try:
            async with session.get('https://id.twitch.tv/oauth2/validate') as response:
                match response.status:
                    case 200:
                        validation_response = await response.json()
                        expires_in = validation_response['expires_in']
                        if expires_in >= 604800:
                            print(f'~~~{datetime.timedelta(seconds=expires_in).days} days until Twitch token expires!~~~')
                        else:
                            print(f'!!! RENEW YOUR TOKEN !!!\n{datetime.timedelta(seconds=expires_in).days} until Twitch token expires.\n!!! RENEW YOUR TOKEN !!!')
                    case 401:
                        print('Twitch access token invalid. Verify the token is valid or hasn\'t expired.')
                        html = await response.json()
                        print(f'{response.status} response!\n',f'{response.headers}\n',f'{html}\n',f'{session.headers}\n')
                        return
                    case _:
                        print(response.status)
                        return
        except aiohttp.ClientConnectorError as e:
            print(f'Connection Error! {str(e)}')
            return

bot.setup_hook = setup_hook

##############################################################################
############################## COMMANDS SECTION ##############################
##############################################################################

@bot.command()
@commands.is_owner()
async def sync(self: commands.Context) -> None:
    """Syncs commands globally"""
    synced = await self.bot.tree.sync()
    await self.send(f'Synced {len(synced)} commands globally')

@bot.command()
@commands.is_owner()
async def refresh_twitch(self: commands.Context) -> None:
    """Refreshes your Twitch API token"""
    twitch_headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    params = {
        'client_id': f'{TWITCH_CLIENT_ID}',
        'client_secret': f'{TWITCH_CLIENT_SECRET}',
        'grant_type': 'client_credentials'
        } 
    async with aiohttp.ClientSession(headers=twitch_headers) as session:
        async with session.post(f'https://id.twitch.tv/oauth2/token', params=params) as response:
            refresh_response = await response.json()
            
            if response.status == 400:
                print(f'Token refresh failed: {refresh_response['message']}')
            elif response.status == 200:
                print(json.dumps(refresh_response,indent=2))
            else:
                print(refresh_response)
                

# @bot.command(description='Shares a favorite Staws memory!')
# async def rere(ctx):
#     ranimg = random.choice(os.listdir('C:\\Users\\Jason\\Pictures\\Rediscover\\'))
#     rere_image = discord.File('C:\\Users\\Jason\\Pictures\\Rediscover\\' + ranimg)
#     await ctx.channel.send(file=rere_image)

# @bot.command(description='Gets a random goldmine entry.')
# async def goldmine(message):
#     embed = discord.Embed()
#     gm_chan = bot.get_channel(306299397724045313)

#     for post in gm_chan:
#         bot.get

@bot.command(description='Returns some basic stats about the user.')
async def whois(command, *, member: discord.Member):
    info = '{0} joined on {0.joined_at} and has {1} roles.'
    await command.send(info.format(member, len(member.roles)))

# @bot.command(description='Admin command for grabbing message history')
# async def grab(ctx):
#     channel = bot.get_channel(154048730771881984)
#     user = bot.get_user(83741220047683584)
#     #messages = await channel.history(limit=20)
    
#     async for msg in channel.history(limit=20):
#         if msg.author.id is user:

#     for msg in messages:
#         if messages.author.id == user:
#             await print(msg)

bot.run(DISCORD_TOKEN, log_handler=handler, log_level=logging.DEBUG)