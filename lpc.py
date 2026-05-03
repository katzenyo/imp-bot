import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Refer to .env file for setting the ALBUMS_PATH variable
ALBUMS_PATH = os.environ["ALBUMS_PATH"]
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")  # Default to 'ffmpeg' if not set

class LPCPlayer(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.queue = []
        self.current_voice_client = None

    def get_albums(self) -> List[str]:
        """Get list of album directories"""
        if not os.path.exists(ALBUMS_PATH):
            return []
        return [d for d in os.listdir(ALBUMS_PATH)
                if os.path.isdir(os.path.join(ALBUMS_PATH, d))]

    def get_audio_files(self, album: str) -> List[Path]:
        """Get all audio files from an album directory"""
        album_path = Path(ALBUMS_PATH) / album
        if not album_path.exists():
            return []

        audio_extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a'}
        audio_files = [
            f for f in album_path.iterdir()
            if f.is_file() and f.suffix.lower() in audio_extensions
        ]
        return sorted(audio_files)

    async def play_next(self, voice_client: discord.VoiceClient):
        """Play the next track in the queue"""
        if not self.queue:
            return

        next_track = self.queue.pop(0)
        audio_source = discord.FFmpegPCMAudio(str(next_track), executable=FFMPEG_PATH)

        voice_client.play(
            audio_source,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                self.play_next(voice_client), self.bot.loop
            )
        )

    @app_commands.command(name="play", description="Play an album")
    @app_commands.describe(album="Select an album to play")
    async def play(self, interaction: discord.Interaction, album: str):
        """Play all tracks from the selected album"""
        # Check if user is in a voice channel
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
            await interaction.response.send_message(
                "You must be connected to a voice channel!",
                ephemeral=True
            )
            return

        # Get audio files from the album
        audio_files = self.get_audio_files(album)
        if not audio_files:
            await interaction.response.send_message(
                f"No audio files found in album: {album}",
                ephemeral=True
            )
            return

        # Connect to voice channel
        voice_channel = interaction.user.voice.channel
        if not voice_channel:
            await interaction.response.send_message(
                "Could not connect to your voice channel.",
                ephemeral=True
            )
            return

        if self.current_voice_client and self.current_voice_client.is_connected():
            await self.current_voice_client.move_to(voice_channel)
        else:
            self.current_voice_client = await voice_channel.connect()

        # Add tracks to queue
        self.queue.extend(audio_files)

        view = self.AudioControlView(self)
        # view.add_item(discord.ui.Button(label="⏹️ Stop", style=discord.ButtonStyle.danger, custom_id="lpc:stop"))
        # view.add_item(discord.ui.Button(label="⏭️ Skip", style=discord.ButtonStyle.primary, custom_id="lpc:skip"))

        await interaction.response.send_message(
            f"🎵 Playing album: **{album}** ({len(audio_files)} tracks)"
        , view=view)

        # Start playing if not already playing
        if not self.current_voice_client.is_playing():
            await self.play_next(self.current_voice_client)

    @play.autocomplete('album')
    async def album_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for album selection"""
        albums = self.get_albums()

        # Filter albums based on user input
        filtered = [
            album for album in albums
            if current.lower() in album.lower()
        ]

        # Return up to 25 choices (Discord limit)
        return [
            app_commands.Choice(name=album, value=album)
            for album in filtered[:25]
        ]

    class AudioControlView(discord.ui.View):
        def __init__(self, cog: 'LPCPlayer'):
            super().__init__(timeout=None)
            self.cog = cog

        @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger, custom_id="lpc:stop")
        async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Stop playback and clear the queue"""
            if self.cog.current_voice_client and self.cog.current_voice_client.is_connected():
                self.cog.queue.clear()
                await self.cog.current_voice_client.disconnect()
                self.cog.current_voice_client = None
                await interaction.response.send_message("⏹️ Stopped playback")
            else:
                await interaction.response.send_message(
                    "Not currently playing anything!",
                    ephemeral=True
                )
        
        @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.primary, custom_id="lpc:skip")
        async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Skip the current track"""
            if self.cog.current_voice_client and self.cog.current_voice_client.is_playing():
                self.cog.current_voice_client.stop()
                await interaction.response.send_message("⏭️ Skipped track")
            else:
                await interaction.response.send_message(
                    "Not currently playing anything!",
                    ephemeral=True
                )

async def setup(bot: commands.Bot):
    await bot.add_cog(LPCPlayer(bot)) 