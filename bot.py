# bot.py
import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import logging
import yt_dlp
from gtts import gTTS
import tempfile
import aiohttp
from typing import Optional, Dict, List

# --- การตั้งค่าเริ่มต้น ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    logger.error("DISCORD_TOKEN not found in environment variables")
    raise ValueError("DISCORD_TOKEN is required")

# --- การตั้งค่า YTDL และ FFMPEG ---
# ใช้ yt-dlp ซึ่งเป็นเวอร์ชันที่พัฒนาต่อจาก youtube-dl
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    """
    คลาสสำหรับจัดการการดึงข้อมูลและสตรีมเสียงจาก YouTube
    """
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
            logger.info(f"Extracting info for URL: {url}")
            
            data = await loop.run_in_executor(
                None, 
                lambda: ytdl.extract_info(url, download=not stream)
            )

            if not data:
                raise ValueError("Could not extract video information")

            if 'entries' in data:
                # ถ้าเป็น playlist ให้เลือกวิดีโอแรก
                if not data['entries']:
                    raise ValueError("Playlist is empty")
                data = data['entries'][0]

            if not data.get('url'):
                raise ValueError("No audio URL found")

            filename = data['url'] if stream else ytdl.prepare_filename(data)
            source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
            
            logger.info(f"Successfully created audio source for: {data.get('title', 'Unknown')}")
            return cls(source, data=data)
            
        except Exception as e:
            logger.error(f"Error in YTDLSource.from_url: {e}")
            raise e

# --- การตั้งค่า Discord Bot ---
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents) # Prefix command ไม่ได้ใช้แล้ว แต่ต้องมีไว้

# --- ตัวแปรสำหรับจัดการเพลง (Global State) ---
# ใช้ dictionary เพื่อรองรับการทำงานหลายเซิร์ฟเวอร์พร้อมกัน
queues: Dict[int, List[YTDLSource]] = {}
current_tracks: Dict[int, Optional[YTDLSource]] = {}

# --- ฟังก์ชันเล่นเพลงถัดไป ---
def play_next(guild_id: int, text_channel):
    """เล่นเพลงถัดไปในคิว"""
    try:
        guild = bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            logger.warning(f"No voice client found for guild {guild_id}")
            return
            
        if queues.get(guild_id):
            player = queues[guild_id].pop(0)
            current_tracks[guild_id] = player
            
            def after_playing(error):
                if error:
                    logger.error(f"Player error: {error}")
                play_next(guild_id, text_channel)
            
            guild.voice_client.play(player, after=after_playing)
            
            # ส่งข้อความใน channel
            embed = discord.Embed(
                title="🎵 กำลังเล่นเพลง", 
                description=player.title, 
                color=discord.Color.blue()
            )
            asyncio.run_coroutine_threadsafe(
                text_channel.send(embed=embed), 
                bot.loop
            )
            logger.info(f"Now playing: {player.title} in guild {guild_id}")
        else:
            current_tracks[guild_id] = None
            logger.info(f"Queue is empty for guild {guild_id}")
    except Exception as e:
        logger.error(f"Error in play_next: {e}")
        current_tracks[guild_id] = None


# --- คำสั่งของบอท (Slash Commands) ---

@bot.tree.command(name="play", description="เล่นเพลงจาก YouTube")
@app_commands.describe(query="ชื่อเพลงหรือลิงก์ YouTube")
async def play(interaction: discord.Interaction, query: str):
    try:
        await interaction.response.defer()
        
        # 1. ตรวจสอบว่าผู้ใช้อยู่ในห้องเสียง
        if not interaction.user.voice:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ ข้อผิดพลาด",
                    description="คุณต้องอยู่ในห้องเสียงก่อน",
                    color=discord.Color.red()
                )
            )
            return
        
        user_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client
        
        # 2. เข้าร่วมหรือย้ายห้องเสียง
        try:
            if not voice_client:
                voice_client = await user_channel.connect()
                logger.info(f"Connected to voice channel: {user_channel.name}")
            elif voice_client.channel != user_channel:
                await voice_client.move_to(user_channel)
                logger.info(f"Moved to voice channel: {user_channel.name}")
        except Exception as e:
            logger.error(f"Failed to connect to voice channel: {e}")
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ ข้อผิดพลาด",
                    description="ไม่สามารถเข้าห้องเสียงได้",
                    color=discord.Color.red()
                )
            )
            return

        # 3. ดึงข้อมูลเพลง
        try:
            await interaction.followup.send("🔍 กำลังค้นหาเพลง...")
            player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        except Exception as e:
            logger.error(f"Failed to get audio source: {e}")
            await interaction.edit_original_response(
                content="",
                embed=discord.Embed(
                    title="❌ ข้อผิดพลาด",
                    description=f"ไม่สามารถเล่นเพลงได้: {str(e)}",
                    color=discord.Color.red()
                )
            )
            return

        # 4. เพิ่มเข้าคิวหรือเล่นทันที
        guild_id = interaction.guild.id
        
        if voice_client.is_playing() or current_tracks.get(guild_id):
            # เพิ่มเข้าคิว
            if guild_id not in queues:
                queues[guild_id] = []
            queues[guild_id].append(player)
            
            embed = discord.Embed(
                title="📝 เพิ่มเข้าคิว",
                description=f"**{player.title}**",
                color=discord.Color.green()
            )
            embed.add_field(name="ตำแหน่งในคิว", value=len(queues[guild_id]), inline=True)
            await interaction.edit_original_response(content="", embed=embed)
        else:
            # เล่นทันที
            current_tracks[guild_id] = player
            
            def after_playing(error):
                if error:
                    logger.error(f"Player error: {error}")
                play_next(guild_id, interaction.channel)
            
            voice_client.play(player, after=after_playing)
            
            embed = discord.Embed(
                title="🎵 กำลังเล่นเพลง",
                description=f"**{player.title}**",
                color=discord.Color.blue()
            )
            if player.duration:
                minutes, seconds = divmod(player.duration, 60)
                embed.add_field(name="ระยะเวลา", value=f"{minutes:02d}:{seconds:02d}", inline=True)
            await interaction.edit_original_response(content="", embed=embed)
            
    except Exception as e:
        logger.error(f"Unexpected error in play command: {e}")
        try:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ เกิดข้อผิดพลาดที่ไม่คาดคิด",
                    description="กรุณาลองใหม่อีกครั้ง",
                    color=discord.Color.red()
                )
            )
        except:
            pass

@bot.tree.command(name="skip", description="ข้ามเพลงปัจจุบัน")
async def skip(interaction: discord.Interaction):
    try:
        voice_client = interaction.guild.voice_client
        
        if not voice_client:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ ข้อผิดพลาด",
                    description="บอทไม่ได้อยู่ในห้องเสียง",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return
            
        if voice_client.is_playing():
            voice_client.stop()  # การ stop จะไปเรียก play_next() โดยอัตโนมัติ
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⏭️ ข้ามเพลง",
                    description="ข้ามเพลงปัจจุบันแล้ว",
                    color=discord.Color.green()
                )
            )
            logger.info(f"Skipped track in guild {interaction.guild.id}")
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ ข้อผิดพลาด",
                    description="ไม่มีเพลงที่กำลังเล่นอยู่",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
    except Exception as e:
        logger.error(f"Error in skip command: {e}")
        await interaction.response.send_message(
            embed=discord.Embed(
                title="❌ เกิดข้อผิดพลาด",
                description="ไม่สามารถข้ามเพลงได้",
                color=discord.Color.red()
            ),
            ephemeral=True
        )

@bot.tree.command(name="stop", description="หยุดเล่นเพลงและล้างคิว")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client:
        guild_id = interaction.guild.id
        if queues.get(guild_id):
            queues[guild_id].clear()
        current_tracks[guild_id] = None
        voice_client.stop()
        await interaction.response.send_message("หยุดเล่นเพลงและล้างคิวแล้ว")

@bot.tree.command(name="list", description="แสดงคิวเพลงปัจจุบัน")
async def list_queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    queue = queues.get(guild_id, [])
    now_playing = current_tracks.get(guild_id)

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

@bot.tree.command(name="speak", description="แปลงข้อความเป็นเสียงพูด (ภาษาไทย)")
@app_commands.describe(text="ข้อความที่ต้องการให้พูด")
async def speak(interaction: discord.Interaction, text: str):
    try:
        await interaction.response.defer(ephemeral=True)
        
        if len(text) > 200:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ ข้อผิดพลาด",
                    description="ข้อความยาวเกินไป (สูงสุด 200 ตัวอักษร)",
                    color=discord.Color.red()
                )
            )
            return
            
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ ข้อผิดพลาด",
                    description="บอทต้องอยู่ในห้องเสียงก่อนถึงจะพูดได้",
                    color=discord.Color.red()
                )
            )
            return
            
        if voice_client.is_playing():
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ ข้อผิดพลาด",
                    description="กำลังเล่นเพลงอยู่ ไม่สามารถพูดได้",
                    color=discord.Color.red()
                )
            )
            return

        # สร้างไฟล์ TTS ใน temporary directory
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            speech_file = temp_file.name
            
        try:
            tts = gTTS(text=text, lang='th', slow=False)
            tts.save(speech_file)
            
            source = discord.FFmpegPCMAudio(speech_file)
            
            def cleanup_after_speak(error):
                if error:
                    logger.error(f"TTS playback error: {error}")
                try:
                    os.unlink(speech_file)
                except:
                    pass
                    
            voice_client.play(source, after=cleanup_after_speak)
            
            await interaction.followup.send(
                embed=discord.Embed(
                    title="🗣️ กำลังพูด",
                    description=f"'{text}'",
                    color=discord.Color.blue()
                ),
                ephemeral=False
            )
            logger.info(f"TTS played: {text[:50]}... in guild {interaction.guild.id}")
            
        except Exception as e:
            logger.error(f"TTS error: {e}")
            try:
                os.unlink(speech_file)
            except:
                pass
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ เกิดข้อผิดพลาด",
                    description="ไม่สามารถสร้างเสียงพูดได้",
                    color=discord.Color.red()
                )
            )
    except Exception as e:
        logger.error(f"Unexpected error in speak command: {e}")
        try:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ เกิดข้อผิดพลาด",
                    description="ไม่สามารถทำงานได้",
                    color=discord.Color.red()
                )
            )
        except:
            pass

@bot.tree.command(name="wake", description="ส่งข้อความส่วนตัวไปปลุกเพื่อน")
@app_commands.describe(user="ผู้ใช้ที่ต้องการปลุก", message="ข้อความ (ไม่บังคับ)")
async def wake(interaction: discord.Interaction, user: discord.Member, message: str = "ตื่นได้แล้ว!"):
    if user.bot:
        await interaction.response.send_message("ปลุกบอทไม่ได้นะ!", ephemeral=True)
        return
    try:
        embed = discord.Embed(
            title="⏰ มีคนมาปลุก!",
            description=f"**{interaction.user.display_name}** จากเซิร์ฟเวอร์ **'{interaction.guild.name}'** ฝากข้อความมาว่า:\n\n> {message}",
            color=discord.Color.gold()
        )
        await user.send(embed=embed)
        await interaction.response.send_message(f"ส่งข้อความไปปลุก {user.mention} แล้ว", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"ไม่สามารถส่ง DM หาก {user.mention} ได้ (อาจจะปิด DM ไว้)", ephemeral=True)

@bot.tree.command(name="leave", description="ให้บอทออกจากห้องเสียง")
async def leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("ออกจากห้องเสียงแล้ว")
    else:
        await interaction.response.send_message("ฉันไม่ได้อยู่ในห้องเสียง", ephemeral=True)

# --- Event Listeners ---
@bot.event
async def on_ready():
    logger.info(f'Bot logged in as {bot.user.name} (ID: {bot.user.id})')
    try:
        synced = await bot.tree.sync()
        logger.info(f'Successfully synced {len(synced)} commands')
        print(f'🤖 {bot.user.name} is ready! Synced {len(synced)} commands.')
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')
        print(f'❌ Failed to sync commands: {e}')

@bot.event
async def on_voice_state_update(member, before, after):
    """จัดการเมื่อมีการเปลี่ยนแปลงใน voice channel"""
    try:
        voice_client = member.guild.voice_client
        
        # ถ้าบอทอยู่ในห้องเสียงและไม่มีคนอื่นเลย ให้ออกจากห้อง
        if (voice_client and 
            voice_client.channel and 
            len([m for m in voice_client.channel.members if not m.bot]) == 0):
            
            logger.info(f"No users left in voice channel, disconnecting from {member.guild.name}")
            
            # ล้างข้อมูลเพลง
            guild_id = member.guild.id
            if guild_id in queues:
                queues[guild_id].clear()
            current_tracks[guild_id] = None
            
            await voice_client.disconnect()
            
    except Exception as e:
        logger.error(f"Error in on_voice_state_update: {e}")

@bot.event
async def on_command_error(ctx, error):
    """จัดการ error ที่เกิดขึ้น"""
    logger.error(f"Command error: {error}")

@bot.event  
async def on_error(event, *args, **kwargs):
    """จัดการ error ทั่วไป"""
    logger.error(f"Discord event error in {event}: {args}")

# --- Main Execution ---
async def main():
    """Main async function"""
    try:
        async with bot:
            await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        logger.error(f"Fatal error: {e}")
