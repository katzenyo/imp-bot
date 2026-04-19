import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = "impbot.db"

MOVIE_GENRES = [
    "Action", "Adventure", "Animation", "Biopic", "Comedy", "Crime", "Drama/Thriller",
    "Documentary", "Drama", "Fantasy", "Horror", "Music/Musical", "Mystery", "Romance",
    "Seasonal", "Sci-Fi", "Shit", "Thriller", "Western"
]

RANK_LABELS = ["1st choice", "2nd choice", "3rd choice"]
RANK_POINTS = [3, 2, 1]


class RankSelect(discord.ui.Select):
    def __init__(self, rank: int):
        super().__init__(
            placeholder=RANK_LABELS[rank],
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=g, value=g) for g in MOVIE_GENRES],
            custom_id=f'poll:rank:{rank}',
            row=rank
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()


class VoteView(discord.ui.View):
    def __init__(self, poll_view: 'PollView', original_message: discord.Message):
        super().__init__(timeout=180)
        self.poll_view = poll_view
        self.original_message = original_message
        self.rank_selects = [RankSelect(i) for i in range(3)]
        for s in self.rank_selects:
            self.add_item(s)

    @discord.ui.button(label='Submit Vote', style=discord.ButtonStyle.success, custom_id='poll:submit', row=3)
    async def submit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        choices = [s.values[0] if s.values else None for s in self.rank_selects]

        if any(c is None for c in choices):
            await interaction.response.send_message('Please make all three selections before submitting.', ephemeral=True)
            return

        if len(set(choices)) < 3:
            await interaction.response.send_message('Each choice must be a different genre.', ephemeral=True)
            return

        self.poll_view.voters[interaction.user.id] = choices  # type: ignore[index]
        await self.original_message.edit(embed=self.poll_view.build_results_embed())
        await interaction.response.send_message('Your vote has been recorded!', ephemeral=True)


class VoteButton(discord.ui.Button):
    def __init__(self, poll_view: 'PollView'):
        super().__init__(label='Vote', style=discord.ButtonStyle.primary, custom_id='poll:vote')
        self.poll_view = poll_view

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.message is None:
            await interaction.response.send_message('Could not find the poll message.', ephemeral=True)
            return
        vote_view = VoteView(self.poll_view, interaction.message)
        await interaction.response.send_message('Rank your top three genres:', view=vote_view, ephemeral=True)


class PollView(discord.ui.View):
    def __init__(self, question: str):
        super().__init__(timeout=None)
        self.question = question
        self.voters: dict[int, list[str]] = {}
        self.add_item(VoteButton(self))

    def build_results_embed(self) -> discord.Embed:
        counts: dict[str, int] = {}
        for ranked_choices in self.voters.values():
            for rank_idx, choice in enumerate(ranked_choices):
                counts[choice] = counts.get(choice, 0) + RANK_POINTS[rank_idx]
        sorted_genres = sorted(MOVIE_GENRES, key=lambda g: counts.get(g, 0), reverse=True)
        embed = discord.Embed(title=self.question, description=f'{len(self.voters)} vote(s) cast')
        for genre in sorted_genres:
            embed.add_field(name=genre, value=f'{counts.get(genre, 0)} pts', inline=True)
        return embed


class Poll(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.db: aiosqlite.Connection = None  # type: ignore[assignment]

    poll_group = app_commands.Group(name='poll', description='Movie genre poll commands')

    async def cog_load(self) -> None:
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS polls (
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                question TEXT NOT NULL,
                PRIMARY KEY (guild_id, name)
            )
        ''')
        await self.db.commit()

    async def cog_unload(self) -> None:
        if self.db:
            await self.db.close()

    async def _name_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        async with self.db.execute(
            'SELECT name FROM polls WHERE guild_id = ? AND name LIKE ?',
            (interaction.guild_id, f'%{current}%')
        ) as cursor:
            rows = await cursor.fetchall()
        return [app_commands.Choice(name=row['name'], value=row['name']) for row in rows][:25]

    @poll_group.command(name='create', description='Create a movie genre poll and save it for reuse')
    @app_commands.describe(
        name='A short name to save this poll under',
        question='The poll question'
    )
    async def create(self, interaction: discord.Interaction, name: str, question: str) -> None:
        await self.db.execute(
            'INSERT OR REPLACE INTO polls (guild_id, name, question) VALUES (?, ?, ?)',
            (interaction.guild_id, name, question)
        )
        await self.db.commit()
        view = PollView(question)
        await interaction.response.send_message(embed=view.build_results_embed(), view=view)

    @poll_group.command(name='run', description='Run a previously saved poll')
    @app_commands.describe(name='The name of the saved poll')
    @app_commands.autocomplete(name=_name_autocomplete)
    async def run(self, interaction: discord.Interaction, name: str) -> None:
        async with self.db.execute(
            'SELECT question FROM polls WHERE guild_id = ? AND name = ?',
            (interaction.guild_id, name)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            await interaction.response.send_message(f'No saved poll named "{name}".', ephemeral=True)
            return

        view = PollView(row['question'])
        await interaction.response.send_message(embed=view.build_results_embed(), view=view)

    @poll_group.command(name='list', description='List all saved polls for this server')
    async def list(self, interaction: discord.Interaction) -> None:
        async with self.db.execute(
            'SELECT name, question FROM polls WHERE guild_id = ?',
            (interaction.guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message('No saved polls for this server.', ephemeral=True)
            return

        embed = discord.Embed(title='Saved Polls')
        for row in rows:
            embed.add_field(name=row['name'], value=row['question'], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @poll_group.command(name='delete', description='Delete a saved poll')
    @app_commands.describe(name='The name of the poll to delete')
    @app_commands.autocomplete(name=_name_autocomplete)
    async def delete(self, interaction: discord.Interaction, name: str) -> None:
        result = await self.db.execute(
            'DELETE FROM polls WHERE guild_id = ? AND name = ?',
            (interaction.guild_id, name)
        )
        await self.db.commit()

        if result.rowcount == 0:
            await interaction.response.send_message(f'No saved poll named "{name}".', ephemeral=True)
            return

        await interaction.response.send_message(f'Poll "{name}" deleted.', ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Poll(bot))
