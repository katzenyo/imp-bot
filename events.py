import os
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TWITCH_ACCESS_TOKEN=os.getenv("TWITCH_ACCESS_TOKEN")
TWITCH_CLIENT_ID=os.getenv("TWITCH_CLIENT_ID")

class EventsCog(commands.Cog):
    def __init__(self,bot: commands.Bot) -> None:
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_presence_update(self,before: discord.Member,after: discord.Member):
        #channel = self.bot.get_channel(154048730771881984)
        guild = after.guild.system_channel
        twitch_headers = {
            'Authorization': f'Bearer {TWITCH_ACCESS_TOKEN}', 
            'Client-Id': f'{TWITCH_CLIENT_ID}'
            }

        if not guild:
            print(f'[ERROR] {after.guild.name}[{after.guild.id}] has no system channel!')
            return

        streaming_activity = next((act for act in after.activities if isinstance(act, discord.Streaming)), None)
        # if not streaming_activity:
        #     print(after.activities,after.activity)
        #     return #No streaming activity found, or invalid activity type

        was_streaming_before = any(isinstance(act, discord.Streaming) for act in before.activities) if before.activities else False
        if was_streaming_before:
            print('The was_streaming_before function returned!')
            return  # User was already streaming, so don't send a duplicate notification

        class TwitchLinkButton(discord.ui.View):
            def __init__(self):
                super().__init__()
                self.value = None
                self.add_item(discord.ui.Button(label='Watch now!',style=discord.ButtonStyle.blurple,url=streaming_activity.url))
        
        if not streaming_activity:
            # print(f'The streaming_activity was {after.activities}, {after.activity}')
            return  # No streaming activity detected
        
        if not hasattr(streaming_activity, 'twitch_name'):
            # print('The twitch_name wasn\'t found!')
            return  # Twitch name is required
        
        # if before.activity is not None:
        #     if before.activity.type != after.activity.type:
        #             for act in after.activities:
        #                 if isinstance(act, discord.Streaming):
        async with aiohttp.ClientSession(headers=twitch_headers) as session:
            try:
                async with session.get(f'https://api.twitch.tv/helix/users?login={streaming_activity.twitch_name}') as response:
                    match response.status:
                        case 200: # Send message to system channel after successful response
                            twitch_user_info = await response.json()
                            thumbnail_url = twitch_user_info['data'][0]['profile_image_url']

                            embed = discord.Embed(
                            title=f'{streaming_activity.details}',
                            url=f'{streaming_activity.url}',
                            description=f'Now streaming {streaming_activity.game}',
                            color=discord.Color.random()
                            )
                            embed.set_author(
                                name=f'{streaming_activity.twitch_name} is now live on {streaming_activity.platform}!',
                                url=f'{streaming_activity.url}'
                                #icon_url=f'{after.activity.assets}'
                            )
                            embed.set_image(
                                url=f'https://static-cdn.jtvnw.net/previews-ttv/live_user_{streaming_activity.twitch_name}-440x248.jpg'
                            )
                            embed.set_thumbnail(
                                url=thumbnail_url
                            )
                            embed.set_footer(
                                text='Imp Bot 10000'
                            )

                            await guild.send(embed=embed,view=TwitchLinkButton()) 
                            print("[SUCCESS] Twitch stream notification sent!")
                        case 400: # Likely API key expired/incorrect
                            print("[ERROR] 400 Unavailable. Is your Twitch API key still valid?")
                        case _: # For non-API key unhealthy responses
                            print(f'[ERROR] Unexpected response: {response.status}')
            except aiohttp.ClientConnectorError as e:
                print(f'[ERROR] Connection Error! {e}')
                return

    #   if activity_type is discord.Streaming or discord.Spotify:
    #    #await after.guild.system_channel.send(f'{after.name} is streaming!')
    #        await print(f'Here\'s the activity value: {after.activity}, the status value: {after.status}, and the guild name: {after.guild.name}')

    async def on_member_join(self,member:discord.Member):
        guild = member.guild
        #channel = bot.get_channel(154048730771881984)
        channel = guild.system_channel
        if guild.system_channel is not None:
            msg = f'Welcome to {member.display_name} to {guild.name}!'
            await channel.send(msg)
    
    async def on_member_remove(self,member:discord.Member):
        guild = member.guild
        channel = guild.system_channel

        if guild.system_channel is not None:
            await channel.send(f'{member.display_name} has abandoned the cause and left {guild.name}!')

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))