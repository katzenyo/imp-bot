import datetime
import calendar
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List

DB_PATH = "impbot.db"
BIRTHDAY_EMBED_COLOR = discord.Color.from_rgb(255, 172, 51)

class BirthdayCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Optional[aiosqlite.Connection] = None

    birthday_group = app_commands.Group(name='birthday', description='Birthday commands')

    async def cog_load(self) -> None:
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row
        await self._create_tables()
        self.birthday_check_task.start()

    async def cog_unload(self) -> None:
        self.birthday_check_task.cancel()
        if self.db:
            await self.db.close()

    async def _create_tables(self) -> None:
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS birthdays (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                month INTEGER NOT NULL,
                day INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS birthday_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL
            )
        ''')
        await self.db.commit()

    async def _get_birthday_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        async with self.db.execute(
            'SELECT channel_id FROM birthday_channels WHERE guild_id = ?',
            (guild.id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            channel = guild.get_channel(row['channel_id'])
            if channel:
                return channel
            await self.db.execute(
                'DELETE FROM birthday_channels WHERE guild_id = ?',
                (guild.id,)
            )
            await self.db.commit()

        return guild.system_channel

    @staticmethod
    def _build_birthday_embed(member: discord.Member) -> discord.Embed:
        embed = discord.Embed(
            title='Happy Birthday!',
            description=f'Today is a special day! Let\'s all wish {member.mention} a wonderful birthday!',
            color=BIRTHDAY_EMBED_COLOR
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text='Imp Bot 10000')
        return embed

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))
    async def birthday_check_task(self) -> None:
        await self.bot.wait_until_ready()

        today = datetime.datetime.now(datetime.timezone.utc)

        async with self.db.execute(
            'SELECT guild_id, user_id FROM birthdays WHERE month = ? AND day = ?',
            (today.month, today.day)
        ) as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            guild = self.bot.get_guild(row['guild_id'])
            if not guild:
                continue

            member = guild.get_member(row['user_id'])
            if not member:
                continue

            channel = await self._get_birthday_channel(guild)
            if not channel:
                print(f'[BIRTHDAY] No birthday channel available for guild {guild.name} [{guild.id}]')
                continue

            try:
                embed = self._build_birthday_embed(member)
                await channel.send(embed=embed)
                print(f'[BIRTHDAY] Sent birthday message for {member.display_name} in {guild.name}')
            except discord.Forbidden:
                print(f'[BIRTHDAY] Missing permissions to send in {channel.name} [{guild.name}]')
            except discord.HTTPException as e:
                print(f'[BIRTHDAY] Failed to send birthday message: {e}')

    @birthday_group.command(name='set', description='Set your birthday (month and day)')
    @app_commands.describe(month='Month', day='Day of the month (1-31)')
    @app_commands.choices(month=[
        app_commands.Choice(name=calendar.month_name[i], value=i)
        for i in range(1, 13)
    ])
    async def birthday_set(self, inter: discord.Interaction, month: app_commands.Choice[int], day: int) -> None:
        if not inter.guild:
            await inter.response.send_message('This command can only be used in a server.', ephemeral=True)
            return

        max_day = calendar.monthrange(2000, month.value)[1]
        if day < 1 or day > max_day:
            await inter.response.send_message(
                f'Invalid day! {month.name} has days 1-{max_day}.',
                ephemeral=True
            )
            return

        await self.db.execute(
            'INSERT OR REPLACE INTO birthdays (guild_id, user_id, month, day) VALUES (?, ?, ?, ?)',
            (inter.guild.id, inter.user.id, month.value, day)
        )
        await self.db.commit()

        await inter.response.send_message(
            f'Your birthday has been set to **{month.name} {day}**!',
            ephemeral=True
        )

    @birthday_group.command(name='remove', description='Remove your birthday')
    async def birthday_remove(self, inter: discord.Interaction) -> None:
        if not inter.guild:
            await inter.response.send_message('This command can only be used in a server.', ephemeral=True)
            return

        result = await self.db.execute(
            'DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?',
            (inter.guild.id, inter.user.id)
        )
        await self.db.commit()

        if result.rowcount > 0:
            await inter.response.send_message('Your birthday has been removed.', ephemeral=True)
        else:
            await inter.response.send_message('You don\'t have a birthday set in this server.', ephemeral=True)

    @birthday_group.command(name='check', description='Check a birthday')
    @app_commands.describe(member='The member to check (defaults to yourself)')
    async def birthday_check(self, inter: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        if not inter.guild:
            await inter.response.send_message('This command can only be used in a server.', ephemeral=True)
            return

        target = member or inter.user

        async with self.db.execute(
            'SELECT month, day FROM birthdays WHERE guild_id = ? AND user_id = ?',
            (inter.guild.id, target.id)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            month_name = calendar.month_name[row['month']]
            await inter.response.send_message(
                f'{target.display_name}\'s birthday is **{month_name} {row["day"]}**!',
                ephemeral=True
            )
        else:
            if target == inter.user:
                await inter.response.send_message(
                    'You haven\'t set your birthday yet! Use `/birthday set` to set it.',
                    ephemeral=True
                )
            else:
                await inter.response.send_message(
                    f'{target.display_name} hasn\'t set their birthday.',
                    ephemeral=True
                )

    @birthday_group.command(name='channel', description='Set the birthday announcement channel (admin only)')
    @app_commands.describe(channel='The channel for birthday announcements (leave empty to reset to system channel)')
    @app_commands.default_permissions(manage_guild=True)
    async def birthday_channel(self, inter: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
        if not inter.guild:
            await inter.response.send_message('This command can only be used in a server.', ephemeral=True)
            return

        if channel:
            await self.db.execute(
                'INSERT OR REPLACE INTO birthday_channels (guild_id, channel_id) VALUES (?, ?)',
                (inter.guild.id, channel.id)
            )
            await self.db.commit()
            await inter.response.send_message(
                f'Birthday announcements will now be sent to {channel.mention}.',
                ephemeral=True
            )
        else:
            await self.db.execute(
                'DELETE FROM birthday_channels WHERE guild_id = ?',
                (inter.guild.id,)
            )
            await self.db.commit()
            system_ch = inter.guild.system_channel
            if system_ch:
                await inter.response.send_message(
                    f'Birthday channel reset. Announcements will use the system channel ({system_ch.mention}).',
                    ephemeral=True
                )
            else:
                await inter.response.send_message(
                    'Birthday channel reset, but this server has no system channel configured. '
                    'Please set one with `/birthday channel` or configure a system channel in server settings.',
                    ephemeral=True
                )

    @birthday_group.command(name='list', description='Show upcoming birthdays in this server')
    async def birthday_list(self, inter: discord.Interaction) -> None:
        if not inter.guild:
            await inter.response.send_message('This command can only be used in a server.', ephemeral=True)
            return

        async with self.db.execute(
            'SELECT user_id, month, day FROM birthdays WHERE guild_id = ? ORDER BY month, day',
            (inter.guild.id,)
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await inter.response.send_message('No birthdays have been set in this server yet!', ephemeral=True)
            return

        today = datetime.datetime.now(datetime.timezone.utc)
        today_tuple = (today.month, today.day)

        upcoming = []
        passed = []
        for row in rows:
            member = inter.guild.get_member(row['user_id'])
            if not member:
                continue
            entry = (member, row['month'], row['day'])
            if (row['month'], row['day']) >= today_tuple:
                upcoming.append(entry)
            else:
                passed.append(entry)

        sorted_entries = upcoming + passed

        if not sorted_entries:
            await inter.response.send_message('No birthdays found for current server members.', ephemeral=True)
            return

        embed = discord.Embed(
            title='Upcoming Birthdays',
            color=BIRTHDAY_EMBED_COLOR
        )
        embed.set_footer(text='Imp Bot 10000')

        lines = []
        for member, month, day in sorted_entries[:15]:
            month_name = calendar.month_name[month]
            lines.append(f'{member.display_name} -- {month_name} {day}')

        embed.description = '\n'.join(lines)

        if len(sorted_entries) > 15:
            embed.description += f'\n\n*...and {len(sorted_entries) - 15} more*'

        await inter.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BirthdayCog(bot))
