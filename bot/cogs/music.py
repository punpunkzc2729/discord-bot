# bot/cogs/music.py
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import firebase_admin
from firebase_admin import firestore
import logging
import certifi # เพิ่ม certifi เข้ามา

# --- Setup ---
logging.basicConfig(level=logging.INFO)
yt_dlp.utils.bug_reports_message = lambda: ''
yt_dlp_logger = logging.getLogger('yt_dlp')
yt_dlp_logger.setLevel(logging.ERROR)

# --- YTDL & FFmpeg Options (อัปเดตส่วนนี้) ---
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,  # ตัวเลือกหลักในการข้ามการตรวจสอบ Certificate
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    # เพิ่มตัวเลือก ca_file เพื่อบอก yt-dlp ให้ใช้ Certificate จาก certifi โดยตรง
    '--ca-file': certifi.where(),
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

db = firestore.client()

class Music(commands.Cog):
    """A cog for handling all music-related commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues = {}
        self.current_track = {}

    def get_queue(self, guild_id: int):
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    async def update_firebase_state(self, guild_id: int):
        queue = self.get_queue(guild_id)
        queue_data = [{"title": item.get('title'), "url": item.get('webpage_url')} for item in queue]
        current_track_data = self.current_track.get(guild_id)
        
        is_paused = False
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client:
            is_paused = guild.voice_client.is_paused()

        state_payload = {
            'current_track': current_track_data,
            'queue': queue_data,
            'is_playing': current_track_data is not None,
            'is_paused': is_paused,
            'timestamp': firestore.SERVER_TIMESTAMP,
        }
        state_ref = db.collection('guilds').document(str(guild_id)).collection('state').document('playback')
        await self.bot.loop.run_in_executor(None, lambda: state_ref.set(state_payload))

    def play_next(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        queue = self.get_queue(guild_id)
        
        if len(queue) > 0:
            self.current_track[guild_id] = queue.pop(0)
            coro = self.play_song(interaction, self.current_track[guild_id])
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
        else:
            self.current_track[guild_id] = None
            asyncio.run_coroutine_threadsafe(self.update_firebase_state(guild_id), self.bot.loop)

    async def play_song(self, interaction: discord.Interaction, song_info: dict):
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client

        if not voice_client:
            return

        try:
            source = await discord.FFmpegOpusAudio.from_probe(song_info['url'], **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda e: self.handle_after_play(e, interaction))
            
            embed = discord.Embed(title="Now Playing", description=f"[{song_info['title']}]({song_info['webpage_url']})", color=discord.Color.blue())
            embed.set_footer(text=f"Requested by {song_info['requester']}")
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)

        except Exception as e:
            logging.error(f"Error playing song in guild {guild_id}: {e}")
            await interaction.channel.send(f"Error playing song: `{e}`")
        finally:
            await self.update_firebase_state(guild_id)

    def handle_after_play(self, error, interaction):
        if error:
            logging.error(f'Error after playing in guild {interaction.guild.id}: {error}')
        self.play_next(interaction)

    @app_commands.command(name="play", description="Plays a song from YouTube or adds it to the queue.")
    @app_commands.describe(query="The URL or search term for the song.")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        guild_id = interaction.guild.id

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("You need to be in a voice channel to use this command.")
            return

        if not interaction.guild.voice_client:
            await interaction.user.voice.channel.connect()

        loop = self.bot.loop or asyncio.get_event_loop()
        try:
            # เพิ่มการดักจับ Error ที่เฉพาะเจาะจงมากขึ้น
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0])
        except yt_dlp.utils.DownloadError as e:
            logging.error(f"yt_dlp DownloadError in guild {guild_id}: {e}")
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                await interaction.followup.send("Failed to get song due to an SSL Certificate error on the host machine. This fix has been applied, please try again. If it persists, the host's network may be blocking the connection.")
            else:
                await interaction.followup.send(f"An error occurred while fetching the song: The video may be private, age-restricted, or unavailable.")
            return
        except Exception as e:
            logging.error(f"yt_dlp generic error in guild {guild_id} for query '{query}': {e}")
            await interaction.followup.send(f"An unknown error occurred while trying to fetch the song.")
            return

        song = {
            'title': info.get('title', 'Unknown Title'),
            'url': info.get('url'),
            'webpage_url': info.get('webpage_url', ''),
            'duration': info.get('duration', 0),
            'requester': interaction.user.display_name
        }

        if interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused():
            self.get_queue(guild_id).append(song)
            await interaction.followup.send(f"Added to queue: **{song['title']}**")
        else:
            self.current_track[guild_id] = song
            await self.play_song(interaction, song)
            
        await self.update_firebase_state(guild_id)

    @app_commands.command(name="pause", description="Pauses the current song.")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("Playback paused.")
            await self.update_firebase_state(interaction.guild.id)
        else:
            await interaction.response.send_message("Nothing is playing to pause.")

    @app_commands.command(name="resume", description="Resumes the paused song.")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("Playback resumed.")
            await self.update_firebase_state(interaction.guild.id)
        else:
            await interaction.response.send_message("Playback is not paused.")

    @app_commands.command(name="skip", description="Skips the current song.")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("Skipped the song.")
        else:
            await interaction.response.send_message("Nothing is playing to skip.")

    @app_commands.command(name="stop", description="Stops playback and clears the queue.")
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.get_queue(guild_id).clear()
        self.current_track[guild_id] = None

        if interaction.guild.voice_client:
            interaction.guild.voice_client.stop()
        
        await interaction.response.send_message("Playback stopped and queue cleared.")
        await self.update_firebase_state(guild_id)

    @app_commands.command(name="list", description="Shows the current music queue.")
    async def list(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        queue = self.get_queue(guild_id)
        current = self.current_track.get(guild_id)
        
        if not queue and not current:
            await interaction.response.send_message("The queue is empty and nothing is playing.")
            return

        embed = discord.Embed(title="Music Queue", color=discord.Color.purple())
        
        if current:
            embed.add_field(name="Now Playing", value=f"[{current['title']}]({current['webpage_url']})", inline=False)

        if queue:
            queue_text = "\n".join(f"{i+1}. {song['title']}" for i, song in enumerate(queue[:10]))
            if len(queue) > 10:
                queue_text += f"\n...and {len(queue) - 10} more."
            embed.add_field(name="Up Next", value=queue_text, inline=False)
            
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
