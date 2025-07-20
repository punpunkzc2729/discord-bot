

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp
from gtts import gTTS
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

# --- การตั้งค่า YTDL และ FFMPEG ---
YTDL_OPTIONS = {
    'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'extract_flat': False,
    'retries': 5,
    'fragment_retries': 5,
    'retry_sleep_functions': {'http': lambda n: min(4, 0.5 * (2 ** n))},
    'extractor_args': {
        'youtube': {
            'player_client': ['ios', 'android', 'mweb', 'web', 'tv_embedded'],
            'skip': ['dash', 'hls'],
            'max_comments': [0],
            'innertube_host': ['youtubei.googleapis.com'],
        }
    },
    'age_limit': None,
    'geo_bypass': True,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us,en;q=0.5',
        'Sec-Fetch-Mode': 'navigate',
    }
}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Unknown Title')
        self.url = data.get('webpage_url', '')
        self.duration = data.get('duration', 0)

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        try:
            loop = loop or asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, 
                lambda: ytdl.extract_info(url, download=not stream)
            )

            if not data:
                raise ValueError("Could not extract video information")

            if 'entries' in data:
                if not data['entries']:
                    raise ValueError("Playlist is empty")
                data = data['entries'][0]

            if not data.get('url'):
                raise ValueError("No audio URL found")

            filename = data['url'] if stream else ytdl.prepare_filename(data)
            source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
            
            return cls(source, data=data)
            
        except Exception as e:
            error_msg = str(e)
            if "Failed to extract any player response" in error_msg:
                raise ValueError("วิดีโอนี้ไม่สามารถเล่นได้ อาจจะถูกลบ ถูกตั้งเป็นส่วนตัว หรือถูกบล็อกในภูมิภาคนี้")
            elif "Video unavailable" in error_msg:
                raise ValueError("วิดีโอไม่พร้อมใช้งาน")
            elif "Private video" in error_msg:
                raise ValueError("วิดีโอนี้เป็นวิดีโอส่วนตัว")
            elif "age-restricted" in error_msg.lower():
                raise ValueError("วิดีโอนี้มีการจำกัดอายุ")
            else:
                raise ValueError(f"ไม่สามารถเล่นวิดีโอได้: {error_msg}")

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues = {}
        self.current_tracks = {}

    def play_next(self, guild_id: int, text_channel):
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild or not guild.voice_client:
                return
            
            if self.queues.get(guild_id):
                player = self.queues[guild_id].pop(0)
                self.current_tracks[guild_id] = player
                
                def after_playing(error):
                    if error:
                        logger.error(f"Player error: {error}")
                    self.play_next(guild_id, text_channel)
                
                guild.voice_client.play(player, after=after_playing)
                
                embed = discord.Embed(
                    title="🎵 กำลังเล่นเพลง", 
                    description=player.title, 
                    color=discord.Color.blue()
                )
                asyncio.run_coroutine_threadsafe(
                    text_channel.send(embed=embed), 
                    self.bot.loop
                )
            else:
                self.current_tracks[guild_id] = None
        except Exception as e:
            logger.error(f"Error in play_next: {e}")
            self.current_tracks[guild_id] = None

    @app_commands.command(name="play", description="เล่นเพลงจาก YouTube")
    @app_commands.describe(query="ชื่อเพลงหรือลิงก์ YouTube")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        try:
            if not interaction.user.voice:
                await interaction.followup.send("คุณต้องอยู่ในห้องเสียงก่อน", ephemeral=True)
                return
            
            user_channel = interaction.user.voice.channel
            voice_client = interaction.guild.voice_client
            
            if not voice_client:
                voice_client = await user_channel.connect()
            elif voice_client.channel != user_channel:
                await voice_client.move_to(user_channel)

            player = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True)

            guild_id = interaction.guild.id
            
            if voice_client.is_playing() or self.current_tracks.get(guild_id):
                if guild_id not in self.queues:
                    self.queues[guild_id] = []
                self.queues[guild_id].append(player)
                
                embed = discord.Embed(title="📝 เพิ่มเข้าคิว", description=f"**{player.title}**", color=discord.Color.green())
                await interaction.followup.send(embed=embed)
            else:
                self.current_tracks[guild_id] = player
                
                def after_playing(error):
                    if error:
                        logger.error(f"Player error: {error}")
                    self.play_next(guild_id, interaction.channel)
                
                voice_client.play(player, after=after_playing)
                
                embed = discord.Embed(title="🎵 กำลังเล่นเพลง", description=f"**{player.title}**", color=discord.Color.blue())
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            await interaction.followup.send(f"เกิดข้อผิดพลาด: {e}", ephemeral=True)

    @app_commands.command(name="skip", description="ข้ามเพลงปัจจุบัน")
    async def skip(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("ข้ามเพลงแล้ว")
        else:
            await interaction.response.send_message("ไม่มีเพลงที่กำลังเล่นอยู่", ephemeral=True)

    @app_commands.command(name="stop", description="หยุดเล่นเพลงและล้างคิว")
    async def stop(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client:
            guild_id = interaction.guild.id
            if self.queues.get(guild_id):
                self.queues[guild_id].clear()
            self.current_tracks[guild_id] = None
            voice_client.stop()
            await interaction.response.send_message("หยุดเล่นเพลงและล้างคิวแล้ว")

    @app_commands.command(name="list", description="แสดงคิวเพลงปัจจุบัน")
    async def list_queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        queue = self.queues.get(guild_id, [])
        now_playing = self.current_tracks.get(guild_id)

        if not now_playing and not queue:
            await interaction.response.send_message("ไม่มีเพลงในคิวเลย")
            return
        
        embed = discord.Embed(title="คิวเพลง", color=discord.Color.purple())
        if now_playing:
            embed.add_field(name="กำลังเล่น", value=now_playing.title, inline=False)
        if queue:
            queue_text = "\n".join(f"{i+1}. {song.title}" for i, song in enumerate(queue[:10]))
            if len(queue) > 10:
                queue_text += f"\n...และอีก {len(queue) - 10} เพลง"
            embed.add_field(name="เพลงถัดไป", value=queue_text, inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="join", description="ให้บอทเข้าห้องเสียง")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            await interaction.response.send_message("คุณต้องอยู่ในห้องเสียงก่อน", ephemeral=True)
            return
        
        user_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client and voice_client.is_connected():
            await voice_client.move_to(user_channel)
        else:
            await user_channel.connect()
        
        await interaction.response.send_message(f"เข้าห้อง {user_channel.name} แล้ว")

    @app_commands.command(name="leave", description="ให้บอทออกจากห้องเสียง")
    async def leave(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("ออกจากห้องเสียงแล้ว")
        else:
            await interaction.response.send_message("ฉันไม่ได้อยู่ในห้องเสียง", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))

