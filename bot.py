# bot.py
import os
import asyncio

# Critical: Proper PyNaCl integration without monkey patching
import sys
import subprocess

def verify_voice_dependencies():
    """Verify and install voice dependencies if needed"""
    try:
        import nacl
        import nacl.secret
        import nacl.utils
        import nacl.encoding
        print("[SUCCESS] PyNaCl loaded successfully")
        return True
    except ImportError:
        print("[WARNING] PyNaCl not found - attempting installation...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--force-reinstall", "PyNaCl==1.5.0"])
            import nacl
            print("[SUCCESS] PyNaCl installed and loaded successfully")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to install PyNaCl: {e}")
            return False

# Verify voice dependencies before proceeding
if not verify_voice_dependencies():
    print("[CRITICAL] Voice dependencies not available. Bot will run without voice support.")

import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
import logging
import yt_dlp
from gtts import gTTS
import tempfile
import aiohttp
import sys
from typing import Optional, Dict, List
import firebase_admin
from firebase_admin import credentials, firestore
import threading

# --- การตั้งค่าเริ่มต้น ---
# Configure console output encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    logger.error("DISCORD_TOKEN not found in environment variables")
    raise ValueError("DISCORD_TOKEN is required")

# --- การเชื่อมต่อ Firebase สำหรับรับคำสั่งจาก Web Dashboard ---
try:
    FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("Firebase connection established for bot")
    else:
        db = None
        logger.warning("Firebase credentials not found, web dashboard integration disabled")
except Exception as e:
    logger.warning(f"Failed to connect to Firebase: {e}")
    db = None

# --- การตั้งค่า YTDL และ FFMPEG ---
# ใช้ yt-dlp ซึ่งเป็นเวอร์ชันที่พัฒนาต่อจาก youtube-dl
# Enhanced YTDL configuration with fallback strategies and better error handling
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
    # Enhanced configuration for latest YouTube API with multiple fallbacks
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
            error_msg = str(e)
            logger.error(f"Error in YTDLSource.from_url: {error_msg}")
            
            # Provide more user-friendly error messages
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

# --- การตั้งค่า Discord Bot ---
# Force voice dependencies to be available
try:
    # ตรวจสอบและ patch Discord.py voice dependencies
    import discord.voice_client
    
    # Monkey patch เพื่อให้ Discord.py รู้ว่า PyNaCl พร้อมใช้งาน
    if hasattr(discord.voice_client, '_nacl'):
        discord.voice_client._nacl = nacl
    
    # ลอง load opus library (จำเป็นสำหรับ voice บน Windows)
    import discord.opus
    if not discord.opus.is_loaded():
        # ลองหา opus library ในระบบ
        opus_libs = ['opus', 'libopus', 'libopus-0', 'libopus.dll', 'opus.dll']
        for lib in opus_libs:
            try:
                discord.opus.load_opus(lib)
                logger.info(f"Successfully loaded opus library: {lib}")
                break
            except:
                continue
        
        if not discord.opus.is_loaded():
            logger.warning("Opus library not found - voice quality may be reduced")
            
    logger.info("Voice system initialized successfully")
    
except Exception as e:
    logger.warning(f"Failed to initialize voice system: {e}")

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.message_content = True  # เพิ่ม message content intent
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


# --- Cogs Loader ---
async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                logger.info(f"Loaded cog: {filename}")
            except Exception as e:
                logger.error(f"Failed to load cog {filename}: {e}")

# --- Event Listeners ---
@bot.event
async def on_ready():
    logger.info(f'Bot logged in as {bot.user.name} (ID: {bot.user.id})')
    try:
        await load_cogs()
        synced = await bot.tree.sync()
        logger.info(f'Successfully synced {len(synced)} commands')
        print(f'[BOT] {bot.user.name} is ready! Synced {len(synced)} commands.')
        
        for command in synced:
            logger.info(f'Synced command: {command.name} - {command.description}')
        
        command_names = [cmd.name for cmd in synced]
        critical_commands = ['play', 'join', 'leave', 'skip', 'stop']
        missing_commands = [cmd for cmd in critical_commands if cmd not in command_names]
        if missing_commands:
            logger.error(f"Missing critical commands: {missing_commands}")
        else:
            logger.info("All critical commands synchronized successfully")
        
        if db:
            listen_for_web_commands.start()
            logger.info("Started Firebase command listener with rate limiting")
        
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')
        print(f'[ERROR] Failed to sync commands: {e}')

# --- Firebase Command Listener ---
async def process_web_command(guild_id: str, command_data: dict):
    """ประมวลผลคำสั่งที่ส่งมาจาก web dashboard"""
    try:
        action = command_data.get('action')
        payload = command_data.get('payload', {})
        
        guild = bot.get_guild(int(guild_id))
        if not guild:
            logger.warning(f"Guild {guild_id} not found")
            return
            
        if action == 'play':
            query = payload.get('query')
            if query:
                await handle_web_play_command(guild, query)
        elif action == 'skip':
            await handle_web_skip_command(guild)
        elif action == 'stop':
            await handle_web_stop_command(guild)
        elif action == 'pause':
            await handle_web_pause_command(guild)
        elif action == 'resume':
            await handle_web_resume_command(guild)
            
        logger.info(f"Processed web command {action} for guild {guild_id}")
        
    except Exception as e:
        logger.error(f"Error processing web command: {e}")

async def handle_web_play_command(guild, query):
    """จัดการคำสั่ง play จาก web"""
    try:
        voice_client = guild.voice_client
        if not voice_client:
            # หาช่องเสียงแรกที่มีสมาชิก
            for channel in guild.voice_channels:
                if len(channel.members) > 0:
                    voice_client = await channel.connect()
                    break
        
        if not voice_client:
            logger.warning("No voice channel available to connect")
            return
            
        # สร้าง audio source
        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        
        guild_id = guild.id
        if voice_client.is_playing() or current_tracks.get(guild_id):
            # เพิ่มเข้าคิว
            if guild_id not in queues:
                queues[guild_id] = []
            queues[guild_id].append(player)
            logger.info(f"Added {player.title} to queue for guild {guild_id}")
        else:
            # เล่นทันที
            current_tracks[guild_id] = player
            
            def after_playing(error):
                if error:
                    logger.error(f"Player error: {error}")
                # หาช่องข้อความที่เหมาะสม
                text_channel = None
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        text_channel = channel
                        break
                play_next(guild_id, text_channel)
            
            voice_client.play(player, after=after_playing)
            logger.info(f"Now playing {player.title} in guild {guild_id}")
            
    except Exception as e:
        logger.error(f"Error in web play command: {e}")

async def handle_web_skip_command(guild):
    """จัดการคำสั่ง skip จาก web"""
    voice_client = guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        logger.info(f"Skipped track in guild {guild.id}")

async def handle_web_stop_command(guild):
    """จัดการคำสั่ง stop จาก web"""
    voice_client = guild.voice_client
    if voice_client:
        guild_id = guild.id
        if queues.get(guild_id):
            queues[guild_id].clear()
        current_tracks[guild_id] = None
        voice_client.stop()
        logger.info(f"Stopped playback in guild {guild_id}")

async def handle_web_pause_command(guild):
    """จัดการคำสั่ง pause จาก web"""
    voice_client = guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        logger.info(f"Paused playback in guild {guild.id}")

async def handle_web_resume_command(guild):
    """จัดการคำสั่ง resume จาก web"""
    voice_client = guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        logger.info(f"Resumed playback in guild {guild.id}")

@tasks.loop(seconds=5)  # Increased to 5 seconds to reduce Firebase quota usage
async def listen_for_web_commands():
    """Enhanced Firebase listener with better error handling and resource management"""
    if not db:
        return
        
    # Add circuit breaker for rate limiting
    if hasattr(listen_for_web_commands, '_rate_limit_until'):
        if asyncio.get_event_loop().time() < listen_for_web_commands._rate_limit_until:
            return  # Skip this iteration due to rate limiting
        
    try:
        # Process only active guilds to reduce load
        active_guilds = [guild for guild in bot.guilds if guild.member_count > 1][:3]  # Limit to 3 guilds max
        
        for guild in active_guilds:
            try:
                guild_id = str(guild.id)
                commands_ref = db.collection('guilds').document(guild_id).collection('commands')
                
                # Run Firebase query in executor to prevent blocking
                loop = asyncio.get_event_loop()
                pending_commands = await loop.run_in_executor(
                    None, 
                    lambda: commands_ref.where('status', '==', 'pending').limit(5).get()
                )
                
                for doc in pending_commands:
                    try:
                        command_data = doc.to_dict()
                        
                        # Add timeout protection for command processing
                        await asyncio.wait_for(
                            process_web_command(guild_id, command_data),
                            timeout=30.0
                        )
                        
                        # Mark as completed with timestamp (run in executor)
                        await loop.run_in_executor(
                            None,
                            lambda: doc.reference.update({
                                'status': 'completed',
                                'completed_at': firestore.SERVER_TIMESTAMP
                            })
                        )
                        logger.info(f"[SUCCESS] Processed web command {command_data.get('action')} for guild {guild_id}")
                        
                    except asyncio.TimeoutError:
                        logger.warning(f"[TIMEOUT] Web command timed out for guild {guild_id}")
                        await loop.run_in_executor(
                            None,
                            lambda: doc.reference.update({'status': 'timeout'})
                        )
                    except Exception as cmd_error:
                        logger.error(f"[ERROR] Error processing command: {cmd_error}")
                        await loop.run_in_executor(
                            None,
                            lambda error=str(cmd_error): doc.reference.update({'status': 'error', 'error': error})
                        )
                        
            except Exception as guild_error:
                logger.error(f"Error processing guild {guild.id}: {guild_error}")
                continue
                
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error in Firebase listener: {e}")
        
        # Handle rate limiting specifically
        if "429" in error_msg or "Quota exceeded" in error_msg:
            # Set rate limit cooldown for 30 seconds
            listen_for_web_commands._rate_limit_until = asyncio.get_event_loop().time() + 30
            logger.warning("Firebase rate limit hit - cooling down for 30 seconds")
            return
            
        # Implement exponential backoff for other errors
        error_count = getattr(listen_for_web_commands, '_error_count', 0)
        sleep_time = min(30, 2 ** error_count)
        await asyncio.sleep(sleep_time)
        setattr(listen_for_web_commands, '_error_count', error_count + 1)

# --- Event Listeners ---
@bot.event
async def on_ready():
    logger.info(f'Bot logged in as {bot.user.name} (ID: {bot.user.id})')
    try:
        # Sync commands normally - DO NOT clear commands
        synced = await bot.tree.sync()
        logger.info(f'Successfully synced {len(synced)} commands')
        print(f'[BOT] {bot.user.name} is ready! Synced {len(synced)} commands.')
        
        # Log all synced commands for debugging
        for command in synced:
            logger.info(f'Synced command: {command.name} - {command.description}')
        
        # Verify critical commands exist
        command_names = [cmd.name for cmd in synced]
        critical_commands = ['play', 'join', 'leave', 'skip', 'stop']
        missing_commands = [cmd for cmd in critical_commands if cmd not in command_names]
        if missing_commands:
            logger.error(f"Missing critical commands: {missing_commands}")
        else:
            logger.info("All critical commands synchronized successfully")
        
        # เริ่ม Firebase listener ถ้ามี (with rate limiting)
        if db:
            listen_for_web_commands.start()
            logger.info("Started Firebase command listener with rate limiting")
        
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')
        print(f'[ERROR] Failed to sync commands: {e}')

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
