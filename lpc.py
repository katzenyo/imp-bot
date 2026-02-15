import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import os
from pathlib import Path
from typing import List

# Placeholder path - update this to your actual albums directory
ALBUMS_PATH = "./albums"

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
        audio_source = discord.FFmpegPCMAudio(str(next_track))

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
        if not interaction.user.voice:
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

        if self.current_voice_client and self.current_voice_client.is_connected():
            await self.current_voice_client.move_to(voice_channel)
        else:
            self.current_voice_client = await voice_channel.connect()

        # Add tracks to queue
        self.queue.extend(audio_files)

        await interaction.response.send_message(
            f"🎵 Playing album: **{album}** ({len(audio_files)} tracks)"
        )

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

    @app_commands.command(name="stop", description="Stop playback and disconnect")
    async def stop(self, interaction: discord.Interaction):
        """Stop playback and clear the queue"""
        if self.current_voice_client and self.current_voice_client.is_connected():
            self.queue.clear()
            await self.current_voice_client.disconnect()
            self.current_voice_client = None
            await interaction.response.send_message("⏹️ Stopped playback")
        else:
            await interaction.response.send_message(
                "Not currently playing anything!",
                ephemeral=True
            )

    @app_commands.command(name="skip", description="Skip to the next track")
    async def skip(self, interaction: discord.Interaction):
        """Skip the current track"""
        if self.current_voice_client and self.current_voice_client.is_playing():
            self.current_voice_client.stop()
            await interaction.response.send_message("⏭️ Skipped track")
        else:
            await interaction.response.send_message(
                "Not currently playing anything!",
                ephemeral=True
            )

    @app_commands.command(name="queue", description="Show the current queue")
    async def show_queue(self, interaction: discord.Interaction):
        """Display the current queue"""
        if not self.queue:
            await interaction.response.send_message(
                "Queue is empty!",
                ephemeral=True
            )
            return

        queue_list = "\n".join([
            f"{i+1}. {track.name}"
            for i, track in enumerate(self.queue[:10])
        ])

        total = len(self.queue)
        message = f"**Queue ({total} tracks):**\n{queue_list}"
        if total > 10:
            message += f"\n... and {total - 10} more"

        await interaction.response.send_message(message)

async def setup(bot: commands.Bot):
    await bot.add_cog(LPCPlayer(bot)) 