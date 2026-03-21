import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

DB_PATH = "impbot.db"
STAR_EMOJI = "⭐"
DEFAULT_THRESHOLD = 3
STARBOARD_COLOR = discord.Color.gold()


class StarboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Optional[aiosqlite.Connection] = None

    starboard_group = app_commands.Group(name="starboard", description="Starboard commands")

    async def cog_load(self) -> None:
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row
        await self._create_tables()

    async def cog_unload(self) -> None:
        if self.db:
            await self.db.close()

    async def _create_tables(self) -> None:
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS starboard_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                threshold INTEGER NOT NULL DEFAULT 3
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS starboard_entries (
                guild_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                starboard_message_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, message_id)
            )
        """)
        await self.db.commit()

    async def _get_config(self, guild_id: int) -> Optional[aiosqlite.Row]:
        async with self.db.execute(
            "SELECT channel_id, threshold FROM starboard_config WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def _get_entry(self, guild_id: int, message_id: int) -> Optional[aiosqlite.Row]:
        async with self.db.execute(
            "SELECT starboard_message_id FROM starboard_entries WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id)
        ) as cursor:
            return await cursor.fetchone()

    def _build_starboard_embed(self, message: discord.Message, star_count: int) -> discord.Embed:
        embed = discord.Embed(
            description=message.content or "",
            color=STARBOARD_COLOR,
            timestamp=message.created_at
        )
        embed.set_author(
            name=message.author.display_name,
            icon_url=message.author.display_avatar.url
        )
        embed.add_field(name="Source", value=f"[Jump to message]({message.jump_url})", inline=False)
        embed.set_footer(text=f"#{message.channel.name}")

        if message.attachments:
            attachment = message.attachments[0]
            if attachment.content_type and attachment.content_type.startswith("image/"):
                embed.set_image(url=attachment.url)

        return embed

    async def _handle_star_update(self, guild_id: int, channel_id: int, message_id: int) -> None:
        config = await self._get_config(guild_id)
        if not config:
            return

        starboard_channel = self.bot.get_channel(config["channel_id"])
        if not starboard_channel:
            return

        if channel_id == config["channel_id"]:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        source_channel = guild.get_channel(channel_id)
        if not source_channel:
            return

        try:
            message = await source_channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        star_reaction = next(
            (r for r in message.reactions if str(r.emoji) == STAR_EMOJI),
            None
        )
        star_count = star_reaction.count if star_reaction else 0

        entry = await self._get_entry(guild_id, message_id)

        if star_count >= config["threshold"]:
            star_label = f"{STAR_EMOJI} **{star_count}**"
            embed = self._build_starboard_embed(message, star_count)

            if entry:
                try:
                    sb_message = await starboard_channel.fetch_message(entry["starboard_message_id"])
                    await sb_message.edit(content=star_label, embed=embed)
                except (discord.NotFound, discord.HTTPException):
                    pass
            else:
                try:
                    sb_message = await starboard_channel.send(content=star_label, embed=embed)
                    await self.db.execute(
                        "INSERT INTO starboard_entries (guild_id, message_id, starboard_message_id) VALUES (?, ?, ?)",
                        (guild_id, message_id, sb_message.id)
                    )
                    await self.db.commit()
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"[STARBOARD] Failed to post message: {e}")
        elif entry:
            try:
                sb_message = await starboard_channel.fetch_message(entry["starboard_message_id"])
                await sb_message.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
            await self.db.execute(
                "DELETE FROM starboard_entries WHERE guild_id = ? AND message_id = ?",
                (guild_id, message_id)
            )
            await self.db.commit()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if str(payload.emoji) != STAR_EMOJI or not payload.guild_id:
            return
        await self._handle_star_update(payload.guild_id, payload.channel_id, payload.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if str(payload.emoji) != STAR_EMOJI or not payload.guild_id:
            return
        await self._handle_star_update(payload.guild_id, payload.channel_id, payload.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_clear(self, payload: discord.RawReactionClearEvent) -> None:
        if not payload.guild_id:
            return
        await self._handle_star_update(payload.guild_id, payload.channel_id, payload.message_id)

    @starboard_group.command(name="channel", description="Set the starboard channel (admin only)")
    @app_commands.describe(channel="The channel where starred messages will be posted")
    @app_commands.default_permissions(manage_guild=True)
    async def starboard_channel(self, inter: discord.Interaction, channel: discord.TextChannel) -> None:
        if not inter.guild:
            await inter.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        await self.db.execute(
            """
            INSERT INTO starboard_config (guild_id, channel_id, threshold)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
            """,
            (inter.guild.id, channel.id, DEFAULT_THRESHOLD)
        )
        await self.db.commit()
        await inter.response.send_message(
            f"Starboard channel set to {channel.mention}.",
            ephemeral=True
        )

    @starboard_group.command(name="threshold", description="Set how many stars a message needs to appear on the starboard (admin only)")
    @app_commands.describe(count="Minimum number of star reactions required (default: 3)")
    @app_commands.default_permissions(manage_guild=True)
    async def starboard_threshold(self, inter: discord.Interaction, count: app_commands.Range[int, 1]) -> None:
        if not inter.guild:
            await inter.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        config = await self._get_config(inter.guild.id)
        if not config:
            await inter.response.send_message(
                "No starboard channel has been set. Use `/starboard channel` first.",
                ephemeral=True
            )
            return

        await self.db.execute(
            "UPDATE starboard_config SET threshold = ? WHERE guild_id = ?",
            (count, inter.guild.id)
        )
        await self.db.commit()
        await inter.response.send_message(
            f"Starboard threshold set to **{count}** {STAR_EMOJI}.",
            ephemeral=True
        )

    @starboard_group.command(name="disable", description="Disable the starboard for this server (admin only)")
    @app_commands.default_permissions(manage_guild=True)
    async def starboard_disable(self, inter: discord.Interaction) -> None:
        if not inter.guild:
            await inter.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        await self.db.execute(
            "DELETE FROM starboard_config WHERE guild_id = ?",
            (inter.guild.id,)
        )
        await self.db.commit()
        await inter.response.send_message("Starboard has been disabled for this server.", ephemeral=True)

    @starboard_group.command(name="status", description="Show the current starboard configuration")
    async def starboard_status(self, inter: discord.Interaction) -> None:
        if not inter.guild:
            await inter.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        config = await self._get_config(inter.guild.id)
        if not config:
            await inter.response.send_message(
                "Starboard is not configured. An admin can set it up with `/starboard channel`.",
                ephemeral=True
            )
            return

        channel = inter.guild.get_channel(config["channel_id"])
        channel_mention = channel.mention if channel else f"*(deleted channel {config['channel_id']})*"
        await inter.response.send_message(
            f"Starboard channel: {channel_mention}\nThreshold: **{config['threshold']}** {STAR_EMOJI}",
            ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StarboardCog(bot))
