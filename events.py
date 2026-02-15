import os
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TWITCH_ACCESS_TOKEN=os.getenv("TWITCH_ACCESS_TOKEN")
TWITCH_CLIENT_ID=os.getenv("TWITCH_CLIENT_ID")

class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.twitch_headers = {
            'Authorization': f'Bearer {TWITCH_ACCESS_TOKEN}',
            'Client-Id': TWITCH_CLIENT_ID
        }

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        channel = after.guild.system_channel

        if not channel:
            print(f'[ERROR] {after.guild.name}[{after.guild.id}] has no system channel!')
            return

        streaming_activity = next((act for act in after.activities if isinstance(act, discord.Streaming)), None)

        if not streaming_activity:
            return

        if not hasattr(streaming_activity, 'twitch_name'):
            return

        was_streaming_before = any(isinstance(act, discord.Streaming) for act in before.activities) if before.activities else False
        if was_streaming_before:
            return

        class TwitchLinkButton(discord.ui.View):
            def __init__(self):
                super().__init__()
                self.add_item(discord.ui.Button(label='Watch now!', style=discord.ButtonStyle.blurple, url=streaming_activity.url))

        async with aiohttp.ClientSession(headers=self.twitch_headers) as session:
            try:
                async with session.get(f'https://api.twitch.tv/helix/users?login={streaming_activity.twitch_name}') as response:
                    match response.status:
                        case 200:
                            twitch_user_info = await response.json()
                            thumbnail_url = twitch_user_info['data'][0]['profile_image_url']

                            embed = discord.Embed(
                                title=streaming_activity.details,
                                url=streaming_activity.url,
                                description=f'Now streaming {streaming_activity.game}',
                                color=discord.Color.random()
                            )
                            embed.set_author(
                                name=f'{streaming_activity.twitch_name} is now live on {streaming_activity.platform}!',
                                url=streaming_activity.url
                            )
                            embed.set_image(
                                url=f'https://static-cdn.jtvnw.net/previews-ttv/live_user_{streaming_activity.twitch_name}-440x248.jpg'
                            )
                            embed.set_thumbnail(url=thumbnail_url)
                            embed.set_footer(text='Imp Bot 10000')

                            await channel.send(embed=embed, view=TwitchLinkButton())
                            print("[SUCCESS] Twitch stream notification sent!")
                        case 400:
                            print("[ERROR] 400 Unavailable. Is your Twitch API key still valid?")
                        case _:
                            print(f'[ERROR] Unexpected response: {response.status}')
            except aiohttp.ClientConnectorError as e:
                print(f'[ERROR] Connection Error! {e}')
                return

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