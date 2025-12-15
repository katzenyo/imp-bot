import os
import discord
import random
import aiohttp
from discord import app_commands
from discord.ext import commands
from discord.app_commands import Group, command
from discord.ext.commands import GroupCog
from dotenv import load_dotenv

load_dotenv()
TWITCH_ACCESS_TOKEN=os.getenv("TWITCH_ACCESS_TOKEN")
TWITCH_CLIENT_ID=os.getenv("TWITCH_CLIENT_ID")
WIKI_ACCESS_TOKEN=os.getenv("WIKI_ACCESS_TOKEN")
WIKI_CLIENT_ID=os.getenv("WIKI_CLIENT_ID")

twitch_headers = {'Authorization': f'Bearer {TWITCH_ACCESS_TOKEN}', 'Client-Id': f'{TWITCH_CLIENT_ID}'}
wiki_headers = {'Authorization': f'Bearer {WIKI_ACCESS_TOKEN}', 'Client-Id': f'{WIKI_CLIENT_ID}'}

class SlashCommands(commands.Cog):
    def __init__(self,bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name='roll', description='Rolls a d20')
    async def roll(self, inter: discord.Interaction) -> None:
        rand = random.randrange(1,21)
        rand_resp = random.randrange(1,11)
        auth = inter.user.display_name
        result = f'> {str(auth)} rolled a **{str(rand)}**! :game_die:'
        match inter.user.id:
            case 115199971535355908:
                if rand_resp <= 2:
                    await inter.response.send_message('> Larry throws the d20 but it\'s too tiny to tell the result! :microscope:')
                else:
                    await inter.response.send_message(result)
            case 154027809587593216:
                if rand_resp <= 2:
                    await inter.response.send_message('> Danny throws the d20 but it explodes into a million little pieces. :boom: How did you fuck this up Danny?')
                else:
                    await inter.response.send_message(result)
            case _:
                await inter.response.send_message(result)

    @app_commands.command(name='clown', description='Identifies a clown!')
    async def clown(self,inter: discord.Interaction) -> None:
        embed = discord.Embed(title='Clown Identified')
        embed.set_image(url=inter.user.display_avatar)
        await inter.response.send_message(embed=embed)

    # @app_commands.command(name='lpc',description='Plays a LPC track.')
    # async def lpc(self,inter: discord.Interaction) -> None:
    #     user = inter.message.author
    #     voice_channel = inter.user.voice.channel

    wiki_group = app_commands.Group(name='wiki',description='Wiki command group')

    @wiki_group.command(name='random',description='Generates a random Wikipedia article')
    async def wiki_random(self, inter:discord.Interaction) -> None:

        class WikiLinkButton(discord.ui.View):
            def __init__(self):
                super().__init__()
                self.value = None

                self.add_item(discord.ui.Button(
                    label='Read more about this bullshit',
                    style=discord.ButtonStyle.blurple,
                    url=f'https://en.wikipedia.org/wiki/{str(article_name).replace(' ','_')}'
                    ))

        async with aiohttp.ClientSession() as session:
            async with session.get('https://en.wikipedia.org/w/api.php?action=query&format=json&prop=images%7Cdescription%7Cextracts%7Cimageinfo&meta=&generator=random&formatversion=2&imlimit=1&exlimit=1&exintro=1&explaintext=1&exsectionformat=plain&iiprop=url&iiurlwidth=440&iiurlheight=248&grnnamespace=0&grnfilterredir=nonredirects&grnlimit=1') as wiki_response:
                match wiki_response.status:
                    case 200:
                        random_article = await wiki_response.json()
                        article_name = random_article['query']['pages'][0]['title']
                        article_body = random_article['query']['pages'][0]['extract']

                        embed = discord.Embed(
                            title=article_name,
                            url=f'https://en.wikipedia.org/wiki/{str(article_name).replace(' ','_')}',
                            description=article_body[:500]+'...',
                            color=discord.Colour.lighter_grey()
                            )
                        embed.set_author(
                            name='Wikipedia',
                            url=f'https://en.wikipedia.org/wiki/{str(article_name).replace(' ','_')}',
                            icon_url='https://upload.wikimedia.org/wikipedia/commons/9/9f/Old_wikipedia_logo.png'
                            )
                        if random_article['query']['pages'][0]['images'][0]['title']:
                            image_name = random_article['query']['pages'][0]['images'][0]['title']
                            embed.set_image(url=f'https://commons.wikimedia.org/wiki/Special:FilePath/{str(image_name).replace(' ','_')}')
                        else:
                            return

                        await inter.response.send_message(embed=embed,view=WikiLinkButton())
                        return
                    case _:
                        print("[ERROR] Wikipedia page returned a non-200 response")
                        return
    
    # @wiki_group.command(name='search',description='Searchs Wikipedia',)
    # async def wiki_search(self, inter:discord.Interaction) -> None:

    #     async with aiohttp.ClientSession() as session:
    #         async with session.get(url='https://api.wikimedia.org/core/v1/wikipedia/en/search/page?q=earth&limit=1') as wiki_response:
    #             match wiki_response.status:
    #                 case 200:
    #                     search_result = await wiki_response.json()
    #                     article_name = search_result['pages'][2]
    #                     article_body = search_result['pages'][3]
                        
    #                     embed = discord.Embed(
    #                         title=article_name,
    #                         url=f'https://en.wikipedia.org/wiki/{str(article_name).replace(' ','_')}',
    #                         description=article_body[:500]+'...',
    #                         color=discord.Colour().light_grey
    #                         )
    #                     embed.set_author(
    #                         name='Wikipedia',
    #                         url=f'https://en.wikipedia.org/wiki/{str(article_name).replace(' ','_')}',
    #                         icon_url='https://upload.wikimedia.org/wikipedia/commons/9/9f/Old_wikipedia_logo.png'
    #                         )
    #                     try:
    #                         random_article['query']['pages'][0]['images'][0]['title']
    #                         image_name = random_article['query']['pages'][0]['images'][0]['title']
    #                         embed.set_image(url=f'https://commons.wikimedia.org/wiki/Special:FilePath/{str(image_name).replace(' ','_')}')
    #                     except:
    #                         return

    #                     await inter.response.send_message(embed=embed,view=WikiLinkButton())
    #                     return
    #                 case _:
    #                     print("[ERROR] Wikipedia page returned a non-200 response")
    #                     return

    
    @app_commands.command(name='bobstream', description='Checks to see if Bob is streaming')
    @app_commands.guilds(discord.Object(287104624865837067)) # ImpZone guild ID
    async def bobstream(self,inter: discord.Interaction) -> None:
        username = 'bn03'
        async with aiohttp.ClientSession(headers=twitch_headers) as session:
            async with session.get(f'https://api.twitch.tv/helix/streams?user_login={username}') as stream_info_response:
                twitch_stream_info = await stream_info_response.json()
                #thumbnail_url = twitch_user_info['data'][0]['profile_image_url']
            async with session.get(f'https://api.twitch.tv/helix/users?login={username}') as user_info_response:
                twitch_user_info = await user_info_response.json()
            
            try:
                embed = discord.Embed(
                    title=f'{twitch_stream_info['data'][0]['title']}',
                    url=f'https://www.twitch.tv/{username}',
                    description=f'Now streaming {twitch_stream_info['data'][0]['game_name']}',
                    color=discord.Color.pink()
                )
                embed.set_author(
                    name=f'Bob is now live on Twitch!',
                    url=f'https://www.twitch.tv/{username}'
                    #icon_url=f'{after.activity.assets}'
                )
                embed.set_image(
                    url=f'https://static-cdn.jtvnw.net/previews-ttv/live_user_{username}-400x250.jpg'
                )
                embed.set_thumbnail(
                    url=twitch_user_info['data'][0]['profile_image_url']
                )
                embed.set_footer(
                    text='CBot 9000'
                )
                await inter.response.send_message(content='Bob is now streaming live!',embed=embed)
                return
            except IndexError:
                await inter.response.send_message('> Bob\'s stream is offline! :sob:')
                return

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SlashCommands(bot))