import re
import aiohttp
import aiosqlite
import discord
import xml.etree.ElementTree as ET
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List

DB_PATH = "impbot.db"
LETTERBOXD_COLOR = discord.Color.from_rgb(0, 210, 120)
LETTERBOXD_NAMESPACES = {
    "letterboxd": "https://letterboxd.com",
    "dc": "http://purl.org/dc/elements/1.1/",
    "tmdb": "https://themoviedb.org",
}
STAR_FULL = "\u2605"
STAR_HALF = "\u00BD"
STAR_EMPTY = "\u2606"
MAX_REVIEW_LENGTH = 400


class LetterboxdCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Optional[aiosqlite.Connection] = None

    letterboxd_group = app_commands.Group(
        name='letterboxd',
        description='Letterboxd feed commands'
    )

    async def cog_load(self) -> None:
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row
        await self._create_tables()
        self.poll_feeds_task.start()

    async def cog_unload(self) -> None:
        self.poll_feeds_task.cancel()
        if self.db:
            await self.db.close()

    async def _create_tables(self) -> None:
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS letterboxd_users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                letterboxd_username TEXT NOT NULL,
                last_guid TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS letterboxd_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL
            )
        ''')
        await self.db.commit()

    async def _get_letterboxd_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        async with self.db.execute(
            'SELECT channel_id FROM letterboxd_channels WHERE guild_id = ?',
            (guild.id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            channel = guild.get_channel(row['channel_id'])
            if channel:
                return channel
            await self.db.execute(
                'DELETE FROM letterboxd_channels WHERE guild_id = ?',
                (guild.id,)
            )
            await self.db.commit()

        return guild.system_channel

    @staticmethod
    def _format_rating(rating: float) -> str:
        full_stars = int(rating)
        has_half = (rating - full_stars) >= 0.5
        empty_stars = 5 - full_stars - (1 if has_half else 0)
        return STAR_FULL * full_stars + (STAR_HALF if has_half else '') + STAR_EMPTY * empty_stars

    @staticmethod
    def _extract_poster_url(description: str) -> Optional[str]:
        match = re.search(r'<img\s+src="([^"]+)"', description)
        return match.group(1) if match else None

    @staticmethod
    def _extract_review_text(description: str) -> Optional[str]:
        paragraphs = re.findall(r'<p>(.*?)</p>', description, re.DOTALL)

        review_parts = []
        for p in paragraphs:
            if '<img' in p:
                continue
            if p.strip().startswith('Watched on'):
                continue
            clean = re.sub(r'<[^>]+>', '', p).strip()
            if clean:
                review_parts.append(clean)

        review = '\n\n'.join(review_parts)
        if not review:
            return None

        if len(review) > MAX_REVIEW_LENGTH:
            review = review[:MAX_REVIEW_LENGTH].rsplit(' ', 1)[0] + '...'

        return review

    @staticmethod
    def _build_embed(
        member: discord.Member,
        film_title: str,
        film_year: str,
        rating: Optional[float],
        review_text: Optional[str],
        poster_url: Optional[str],
        letterboxd_link: str,
        is_rewatch: bool,
    ) -> discord.Embed:
        title = f"{film_title} ({film_year})"

        desc_parts = []
        if rating is not None:
            desc_parts.append(LetterboxdCog._format_rating(rating))
        if is_rewatch:
            desc_parts.append("\U0001F501 Rewatch")
        if review_text:
            desc_parts.append(f"\n{review_text}")

        embed = discord.Embed(
            title=title,
            url=letterboxd_link,
            description='\n'.join(desc_parts) if desc_parts else None,
            color=LETTERBOXD_COLOR,
        )

        embed.set_author(
            name=member.display_name,
            icon_url=member.display_avatar.url,
        )

        if poster_url:
            embed.set_thumbnail(url=poster_url)

        embed.set_footer(text='Imp Bot 10000')

        return embed

    @staticmethod
    async def _fetch_and_parse_feed(username: str) -> Optional[List[ET.Element]]:
        url = f"https://letterboxd.com/{username}/rss/"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status != 200:
                        print(f'[LETTERBOXD] Non-200 response ({resp.status}) for {username}')
                        return None
                    text = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as e:
            print(f'[LETTERBOXD] Connection error fetching {username}: {e}')
            return None

        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            print(f'[LETTERBOXD] XML parse error for {username}: {e}')
            return None

        channel = root.find('channel')
        if channel is None:
            return None

        return channel.findall('item')

    @staticmethod
    def _qualifies_for_post(item: ET.Element) -> bool:
        rating_text = item.findtext(
            'letterboxd:memberRating',
            namespaces=LETTERBOXD_NAMESPACES
        )
        if rating_text:
            try:
                if float(rating_text) > 0:
                    return True
            except ValueError:
                pass

        guid = item.findtext('guid') or ''
        if guid.startswith('letterboxd-review-'):
            return True

        return False

    @tasks.loop(minutes=30)
    async def poll_feeds_task(self) -> None:
        await self.bot.wait_until_ready()

        async with self.db.execute(
            'SELECT guild_id, user_id, letterboxd_username, last_guid FROM letterboxd_users'
        ) as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            guild = self.bot.get_guild(row['guild_id'])
            if not guild:
                continue

            member = guild.get_member(row['user_id'])
            if not member:
                continue

            channel = await self._get_letterboxd_channel(guild)
            if not channel:
                print(f'[LETTERBOXD] No channel available for guild {guild.name} [{guild.id}]')
                continue

            items = await self._fetch_and_parse_feed(row['letterboxd_username'])
            if items is None or not items:
                continue

            last_guid = row['last_guid']

            # Collect new items (feed is newest-first, stop at last seen guid)
            new_items = []
            for item in items:
                guid = item.findtext('guid')
                if guid == last_guid:
                    break
                new_items.append(item)

            if not new_items:
                continue

            # First follow: only post the most recent entry to avoid flooding
            if last_guid is None:
                new_items = [new_items[0]]

            # Reverse to post oldest first (chronological order)
            new_items.reverse()

            for item in new_items:
                if not self._qualifies_for_post(item):
                    continue

                film_title = item.findtext(
                    'letterboxd:filmTitle',
                    namespaces=LETTERBOXD_NAMESPACES
                ) or 'Unknown Title'
                film_year = item.findtext(
                    'letterboxd:filmYear',
                    namespaces=LETTERBOXD_NAMESPACES
                ) or '????'
                rating_text = item.findtext(
                    'letterboxd:memberRating',
                    namespaces=LETTERBOXD_NAMESPACES
                )
                rating = float(rating_text) if rating_text else None
                rewatch_text = item.findtext(
                    'letterboxd:rewatch',
                    namespaces=LETTERBOXD_NAMESPACES
                )
                is_rewatch = rewatch_text == 'Yes'
                link = item.findtext('link') or ''
                description = item.findtext('description') or ''
                poster_url = self._extract_poster_url(description)
                review_text = self._extract_review_text(description)

                embed = self._build_embed(
                    member=member,
                    film_title=film_title,
                    film_year=film_year,
                    rating=rating,
                    review_text=review_text,
                    poster_url=poster_url,
                    letterboxd_link=link,
                    is_rewatch=is_rewatch,
                )

                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    print(f'[LETTERBOXD] Missing permissions in {channel.name} [{guild.name}]')
                    break
                except discord.HTTPException as e:
                    print(f'[LETTERBOXD] Failed to send embed: {e}')
                    continue

            # Update last_guid to newest feed item
            newest_guid = items[0].findtext('guid')
            if newest_guid and newest_guid != last_guid:
                await self.db.execute(
                    'UPDATE letterboxd_users SET last_guid = ? WHERE guild_id = ? AND user_id = ?',
                    (newest_guid, row['guild_id'], row['user_id'])
                )
                await self.db.commit()

    @letterboxd_group.command(name='follow', description='Link your Letterboxd profile')
    @app_commands.describe(username='Your Letterboxd username')
    async def letterboxd_follow(self, inter: discord.Interaction, username: str) -> None:
        if not inter.guild:
            await inter.response.send_message(
                'This command can only be used in a server.', ephemeral=True
            )
            return

        await inter.response.defer(ephemeral=True)
        items = await self._fetch_and_parse_feed(username)
        if items is None:
            await inter.followup.send(
                f'Could not find a Letterboxd profile for **{username}**. '
                'Make sure the username is correct and the profile is public.',
                ephemeral=True,
            )
            return

        await self.db.execute(
            'INSERT OR REPLACE INTO letterboxd_users (guild_id, user_id, letterboxd_username, last_guid) '
            'VALUES (?, ?, ?, NULL)',
            (inter.guild.id, inter.user.id, username)
        )
        await self.db.commit()

        await inter.followup.send(
            f'Now following **{username}** on Letterboxd! '
            'New rated films and reviews will be posted automatically.',
            ephemeral=True,
        )

    @letterboxd_group.command(name='unfollow', description='Unlink your Letterboxd profile')
    async def letterboxd_unfollow(self, inter: discord.Interaction) -> None:
        if not inter.guild:
            await inter.response.send_message(
                'This command can only be used in a server.', ephemeral=True
            )
            return

        result = await self.db.execute(
            'DELETE FROM letterboxd_users WHERE guild_id = ? AND user_id = ?',
            (inter.guild.id, inter.user.id)
        )
        await self.db.commit()

        if result.rowcount > 0:
            await inter.response.send_message(
                'Your Letterboxd profile has been unlinked.', ephemeral=True
            )
        else:
            await inter.response.send_message(
                'You don\'t have a Letterboxd profile linked in this server.',
                ephemeral=True,
            )

    @letterboxd_group.command(
        name='channel',
        description='Set the Letterboxd announcement channel (admin only)'
    )
    @app_commands.describe(
        channel='The channel for Letterboxd posts (leave empty to reset to system channel)'
    )
    @app_commands.default_permissions(manage_guild=True)
    async def letterboxd_channel(
        self, inter: discord.Interaction, channel: Optional[discord.TextChannel] = None
    ) -> None:
        if not inter.guild:
            await inter.response.send_message(
                'This command can only be used in a server.', ephemeral=True
            )
            return

        if channel:
            await self.db.execute(
                'INSERT OR REPLACE INTO letterboxd_channels (guild_id, channel_id) VALUES (?, ?)',
                (inter.guild.id, channel.id)
            )
            await self.db.commit()
            await inter.response.send_message(
                f'Letterboxd posts will now be sent to {channel.mention}.',
                ephemeral=True,
            )
        else:
            await self.db.execute(
                'DELETE FROM letterboxd_channels WHERE guild_id = ?',
                (inter.guild.id,)
            )
            await self.db.commit()
            system_ch = inter.guild.system_channel
            if system_ch:
                await inter.response.send_message(
                    f'Letterboxd channel reset. Posts will use the system channel ({system_ch.mention}).',
                    ephemeral=True,
                )
            else:
                await inter.response.send_message(
                    'Letterboxd channel reset, but this server has no system channel configured. '
                    'Please set one with `/letterboxd channel` or configure a system channel in server settings.',
                    ephemeral=True,
                )

    @letterboxd_group.command(name='list', description='Show all followed Letterboxd users in this server')
    async def letterboxd_list(self, inter: discord.Interaction) -> None:
        if not inter.guild:
            await inter.response.send_message(
                'This command can only be used in a server.', ephemeral=True
            )
            return

        async with self.db.execute(
            'SELECT user_id, letterboxd_username FROM letterboxd_users WHERE guild_id = ? ORDER BY letterboxd_username',
            (inter.guild.id,)
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await inter.response.send_message(
                'No one in this server has linked their Letterboxd profile yet!',
                ephemeral=True,
            )
            return

        lines = []
        for row in rows:
            member = inter.guild.get_member(row['user_id'])
            if not member:
                continue
            lb_user = row['letterboxd_username']
            lines.append(
                f'{member.display_name} -- [{lb_user}](https://letterboxd.com/{lb_user}/)'
            )

        if not lines:
            await inter.response.send_message(
                'No linked Letterboxd profiles found for current server members.',
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title='Letterboxd Profiles',
            description='\n'.join(lines),
            color=LETTERBOXD_COLOR,
        )
        embed.set_footer(text='Imp Bot 10000')

        await inter.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LetterboxdCog(bot))
