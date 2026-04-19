import discord
from discord import app_commands
from discord.ext import commands

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
        first_counts: dict[str, int] = {}
        for ranked_choices in self.voters.values():
            first_counts[ranked_choices[0]] = first_counts.get(ranked_choices[0], 0) + 1
            for rank_idx, choice in enumerate(ranked_choices):
                counts[choice] = counts.get(choice, 0) + RANK_POINTS[rank_idx]
        sorted_genres = sorted(
            MOVIE_GENRES,
            key=lambda g: (counts.get(g, 0), first_counts.get(g, 0)),
            reverse=True
        )
        embed = discord.Embed(title=self.question, description=f'{len(self.voters)} vote(s) cast')
        for genre in sorted_genres:
            pts = counts.get(genre, 0)
            first = first_counts.get(genre, 0)
            embed.add_field(name=genre, value=f'{pts} pts · {first} ★', inline=True)
        return embed


class Poll(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    @app_commands.command(name='poll', description='Start a movie genre poll')
    @app_commands.describe(question='The poll question')
    async def poll(self, interaction: discord.Interaction, question: str) -> None:
        view = PollView(question)
        await interaction.response.send_message(embed=view.build_results_embed(), view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Poll(bot))
