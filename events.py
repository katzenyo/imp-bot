import asyncio
import os
import aiohttp
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from typing import Optional

load_dotenv()
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")

DB_PATH = "impbot.db"
EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: aiosqlite.Connection = None  # type: ignore[assignment]
        self.twitch_headers = {
            'Authorization': f'Bearer {TWITCH_ACCESS_TOKEN}',
            'Client-Id': TWITCH_CLIENT_ID or '',
        }
        self._eventsub_task: Optional[asyncio.Task] = None
        self._session_id: Optional[str] = None

    stream_group = app_commands.Group(name='stream', description='Stream notification commands')

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def cog_load(self) -> None:
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row
        await self._create_tables()
        self._eventsub_task = asyncio.create_task(self._eventsub_loop())

    async def cog_unload(self) -> None:
        if self._eventsub_task:
            self._eventsub_task.cancel()
        if self.db:
            await self.db.close()

    async def _create_tables(self) -> None:
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS stream_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS watched_streams (
                twitch_user_id TEXT NOT NULL,
                twitch_login TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                PRIMARY KEY (twitch_user_id, guild_id)
            )
        ''')
        await self.db.commit()

    # -------------------------------------------------------------------------
    # DB helpers
    # -------------------------------------------------------------------------

    async def _get_stream_channel(self, guild_id: int) -> Optional[discord.TextChannel]:
        async with self.db.execute(
            'SELECT channel_id FROM stream_channels WHERE guild_id = ?', (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None
        channel = guild.get_channel(row['channel_id'])
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _get_all_watched_user_ids(self) -> list[str]:
        async with self.db.execute('SELECT DISTINCT twitch_user_id FROM watched_streams') as cursor:
            rows = await cursor.fetchall()
        return [row['twitch_user_id'] for row in rows]

    async def _get_guilds_for_user(self, twitch_user_id: str) -> list[int]:
        async with self.db.execute(
            'SELECT guild_id FROM watched_streams WHERE twitch_user_id = ?', (twitch_user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [row['guild_id'] for row in rows]

    # -------------------------------------------------------------------------
    # EventSub WebSocket
    # -------------------------------------------------------------------------

    async def _eventsub_loop(self) -> None:
        await self.bot.wait_until_ready()
        backoff = 5
        ws_url = EVENTSUB_WS_URL
        resubscribe = True

        while True:
            try:
                reconnect_url = await self._eventsub_session(ws_url, resubscribe)
                if reconnect_url:
                    # Planned reconnect — subscriptions migrate automatically
                    ws_url = reconnect_url
                    resubscribe = False
                    backoff = 5
                else:
                    ws_url = EVENTSUB_WS_URL
                    resubscribe = True
            except asyncio.CancelledError:
                return
            except Exception as e:
                self._session_id = None
                print(f'[EVENTSUB] Disconnected: {e}, retrying in {backoff}s')
                ws_url = EVENTSUB_WS_URL
                resubscribe = True
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)

    async def _eventsub_session(self, ws_url: str, resubscribe: bool) -> Optional[str]:
        """Runs one EventSub session. Returns reconnect URL if Twitch requested one, else None."""
        async with aiohttp.ClientSession(headers=self.twitch_headers) as http_session:
            async with http_session.ws_connect(ws_url) as ws:
                self._session_id = await self._handshake(ws)
                print(f'[EVENTSUB] Connected (session {self._session_id})')

                if resubscribe:
                    await self._subscribe_all(http_session, self._session_id)

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msg.json()
                        msg_type = data.get('metadata', {}).get('message_type')
                        match msg_type:
                            case 'notification':
                                await self._handle_notification(data.get('payload', {}))
                            case 'session_reconnect':
                                return data['payload']['session']['reconnect_url']
                            case 'session_keepalive' | 'session_welcome':
                                pass
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        raise aiohttp.ClientError(f'WebSocket closed: {ws.close_code}')

        self._session_id = None
        return None

    async def _handshake(self, ws: aiohttp.ClientWebSocketResponse) -> str:
        async def _await_welcome() -> str:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = msg.json()
                    if data.get('metadata', {}).get('message_type') == 'session_welcome':
                        return data['payload']['session']['id']
            raise RuntimeError('WebSocket closed before session_welcome')

        return await asyncio.wait_for(_await_welcome(), timeout=15)

    async def _subscribe_all(self, session: aiohttp.ClientSession, session_id: str) -> None:
        for user_id in await self._get_all_watched_user_ids():
            await self._subscribe(session, session_id, user_id)

    async def _subscribe(self, session: aiohttp.ClientSession, session_id: str, user_id: str) -> None:
        payload = {
            'type': 'stream.online',
            'version': '1',
            'condition': {'broadcaster_user_id': user_id},
            'transport': {'method': 'websocket', 'session_id': session_id},
        }
        async with session.post(
            'https://api.twitch.tv/helix/eventsub/subscriptions', json=payload
        ) as resp:
            if resp.status not in (200, 202):
                body = await resp.json()
                print(f'[EVENTSUB] Failed to subscribe to {user_id}: {resp.status} {body}')

    async def _cancel_subscription(self, twitch_user_id: str) -> None:
        async with aiohttp.ClientSession(headers=self.twitch_headers) as session:
            async with session.get(
                f'https://api.twitch.tv/helix/eventsub/subscriptions?user_id={twitch_user_id}'
            ) as resp:
                if resp.status != 200:
                    print(f'[EVENTSUB] Failed to list subscriptions for {twitch_user_id}: {resp.status}')
                    return
                data = await resp.json()

            for sub in data.get('data', []):
                if sub.get('type') != 'stream.online':
                    continue
                async with session.delete(
                    f'https://api.twitch.tv/helix/eventsub/subscriptions?id={sub["id"]}'
                ) as resp:
                    if resp.status == 204:
                        print(f'[EVENTSUB] Cancelled subscription {sub["id"]} for {twitch_user_id}')
                    else:
                        print(f'[EVENTSUB] Failed to cancel subscription {sub["id"]}: {resp.status}')

    async def _handle_notification(self, payload: dict) -> None:
        event = payload.get('event', {})
        user_id = event.get('broadcaster_user_id')
        login = event.get('broadcaster_user_login')
        if not user_id or not login:
            return

        guild_ids = await self._get_guilds_for_user(user_id)
        if not guild_ids:
            return

        async with aiohttp.ClientSession(headers=self.twitch_headers) as session:
            async with session.get(
                f'https://api.twitch.tv/helix/streams?user_login={login}'
            ) as resp:
                if resp.status != 200:
                    return
                stream_data = await resp.json()
                if not stream_data.get('data'):
                    return
                stream = stream_data['data'][0]

            async with session.get(f'https://api.twitch.tv/helix/users?login={login}') as resp:
                user_data = await resp.json()
                avatar_url = user_data['data'][0]['profile_image_url'] if user_data.get('data') else None

        class TwitchLinkButton(discord.ui.View):
            def __init__(self):
                super().__init__()
                self.add_item(discord.ui.Button(
                    label='Watch now!',
                    style=discord.ButtonStyle.blurple,
                    url=f'https://www.twitch.tv/{login}'
                ))

        embed = discord.Embed(
            title=stream.get('title', 'Untitled stream'),
            url=f'https://www.twitch.tv/{login}',
            description=f'Now streaming {stream.get("game_name", "something")}',
            color=discord.Color.purple()
        )
        embed.set_author(name=f'{login} is now live on Twitch!', url=f'https://www.twitch.tv/{login}')
        embed.set_image(url=f'https://static-cdn.jtvnw.net/previews-ttv/live_user_{login}-440x248.jpg')
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text='Imp Bot 10000')

        for guild_id in guild_ids:
            channel = await self._get_stream_channel(guild_id)
            if channel:
                try:
                    await channel.send(embed=embed, view=TwitchLinkButton())
                    print(f'[EVENTSUB] Sent notification for {login} in guild {guild_id}')
                except discord.HTTPException as e:
                    print(f'[EVENTSUB] Failed to send notification in guild {guild_id}: {e}')

    # -------------------------------------------------------------------------
    # Admin commands
    # -------------------------------------------------------------------------

    @stream_group.command(name='channel', description='Set the stream notification channel')
    @app_commands.describe(channel='Channel where stream notifications will be posted')
    @app_commands.default_permissions(manage_guild=True)
    async def stream_channel(self, inter: discord.Interaction, channel: discord.TextChannel) -> None:
        if not inter.guild:
            await inter.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
        await self.db.execute(
            'INSERT OR REPLACE INTO stream_channels (guild_id, channel_id) VALUES (?, ?)',
            (inter.guild.id, channel.id)
        )
        await self.db.commit()
        await inter.response.send_message(
            f'Stream notifications will be sent to {channel.mention}.', ephemeral=True
        )

    @stream_group.command(name='add', description='Add a Twitch channel to watch')
    @app_commands.describe(twitch_login='Twitch username to watch')
    @app_commands.default_permissions(manage_guild=True)
    async def stream_add(self, inter: discord.Interaction, twitch_login: str) -> None:
        if not inter.guild:
            await inter.response.send_message('This command can only be used in a server.', ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        async with aiohttp.ClientSession(headers=self.twitch_headers) as session:
            async with session.get(f'https://api.twitch.tv/helix/users?login={twitch_login}') as resp:
                if resp.status != 200:
                    await inter.followup.send(f'Failed to look up `{twitch_login}`.', ephemeral=True)
                    return
                data = await resp.json()
                if not data.get('data'):
                    await inter.followup.send(f'Twitch user `{twitch_login}` not found.', ephemeral=True)
                    return
                user = data['data'][0]

            await self.db.execute(
                'INSERT OR IGNORE INTO watched_streams (twitch_user_id, twitch_login, guild_id) VALUES (?, ?, ?)',
                (user['id'], user['login'], inter.guild.id)
            )
            await self.db.commit()

            # Subscribe immediately if there's an active EventSub session
            if self._session_id:
                await self._subscribe(session, self._session_id, user['id'])

        await inter.followup.send(f'Now watching **{user["login"]}** for streams.', ephemeral=True)

    @stream_group.command(name='remove', description='Remove a watched Twitch channel')
    @app_commands.describe(twitch_login='Twitch username to stop watching')
    @app_commands.default_permissions(manage_guild=True)
    async def stream_remove(self, inter: discord.Interaction, twitch_login: str) -> None:
        if not inter.guild:
            await inter.response.send_message('This command can only be used in a server.', ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        async with self.db.execute(
            'SELECT twitch_user_id FROM watched_streams WHERE twitch_login = ? AND guild_id = ?',
            (twitch_login.lower(), inter.guild.id)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await inter.followup.send(f'`{twitch_login}` was not in your watch list.', ephemeral=True)
            return

        twitch_user_id = row['twitch_user_id']
        await self.db.execute(
            'DELETE FROM watched_streams WHERE twitch_login = ? AND guild_id = ?',
            (twitch_login.lower(), inter.guild.id)
        )
        await self.db.commit()

        # Cancel the EventSub subscription only if no other guild is still watching this user
        if not await self._get_guilds_for_user(twitch_user_id):
            await self._cancel_subscription(twitch_user_id)

        await inter.followup.send(f'Stopped watching **{twitch_login}**.', ephemeral=True)

    @stream_group.command(name='list', description='List watched Twitch channels for this server')
    async def stream_list(self, inter: discord.Interaction) -> None:
        if not inter.guild:
            await inter.response.send_message('This command can only be used in a server.', ephemeral=True)
            return
        async with self.db.execute(
            'SELECT twitch_login FROM watched_streams WHERE guild_id = ? ORDER BY twitch_login',
            (inter.guild.id,)
        ) as cursor:
            rows = await cursor.fetchall()
        if not rows:
            await inter.response.send_message('No streams are being watched in this server.', ephemeral=True)
            return
        logins = [row['twitch_login'] for row in rows]
        await inter.response.send_message(
            'Watched streams:\n' + '\n'.join(f'• {l}' for l in logins),
            ephemeral=True
        )

    # -------------------------------------------------------------------------
    # Member listeners
    # -------------------------------------------------------------------------

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
