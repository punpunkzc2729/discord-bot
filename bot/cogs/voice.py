# bot/cogs/voice.py
import discord
from discord.ext import commands
from discord import app_commands
from gtts import gTTS
import os
import logging

class Voice(commands.Cog):
    """A cog for handling voice channel connections and text-to-speech."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="join", description="Joins the voice channel you are in.")
    async def join(self, interaction: discord.Interaction):
        """
        Makes the bot join the user's current voice channel.
        It checks if the user is in a channel first and will move channels if already connected.
        """
        if not interaction.user.voice:
            await interaction.response.send_message("You are not connected to a voice channel.", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        if interaction.guild.voice_client:
            # If already in a channel, move to the user's channel
            await interaction.guild.voice_client.move_to(channel)
        else:
            # If not in a channel, connect
            await channel.connect()
        
        await interaction.response.send_message(f"Connected to **{channel.name}**.")

    @app_commands.command(name="leave", description="Leaves the current voice channel.")
    async def leave(self, interaction: discord.Interaction):
        """
        Disconnects the bot from its current voice channel.
        Also handles stopping any music that might be playing.
        """
        if not interaction.guild.voice_client:
            await interaction.response.send_message("I am not in a voice channel.", ephemeral=True)
            return

        # Stop any potential music playback cleanly
        music_cog = self.bot.get_cog('Music')
        if music_cog:
            guild_id = interaction.guild.id
            music_cog.get_queue(guild_id).clear()
            music_cog.current_track[guild_id] = None
            if interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused():
                 interaction.guild.voice_client.stop()
            # Update firebase to reflect the stopped state
            await music_cog.update_firebase_state(guild_id)

        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Disconnected from the voice channel.")

    @app_commands.command(name="speak", description="Converts text to speech and plays it in the voice channel.")
    @app_commands.describe(text="The text you want the bot to say.")
    async def speak(self, interaction: discord.Interaction, text: str):
        """
        Uses Google Text-to-Speech (gTTS) to say a message in the voice channel.
        The audio is saved to a temporary file, played, and then deleted.
        """
        await interaction.response.defer() 
        
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.followup.send("I need to be in a voice channel to speak.", ephemeral=True)
            return
            
        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send("I'm busy playing music right now and can't speak.", ephemeral=True)
            return

        speech_file = f"temp_speech_{interaction.guild.id}.mp3"
        try:
            # Generate the speech audio file
            loop = self.bot.loop or asyncio.get_event_loop()
            tts = await loop.run_in_executor(None, lambda: gTTS(text=text, lang='en'))
            await loop.run_in_executor(None, lambda: tts.save(speech_file))
            
            # Play the audio file
            source = discord.FFmpegPCMAudio(speech_file)
            voice_client.play(source, after=lambda e: self.delete_speech_file(e, speech_file))
            
            await interaction.followup.send(f"Speaking: '{text}'")
        except Exception as e:
            logging.error(f"Error during text-to-speech in guild {interaction.guild.id}: {e}")
            await interaction.followup.send(f"An error occurred during text-to-speech: {e}")
            self.delete_speech_file(None, speech_file) # Clean up file on error

    def delete_speech_file(self, error, file_path):
        """Callback to delete the temporary speech file after it has been played."""
        if error:
            logging.error(f"Error after speaking: {error}")
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logging.error(f"Error deleting speech file {file_path}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice(bot))
