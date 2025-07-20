

import discord
from discord.ext import commands
from discord import app_commands
from gtts import gTTS
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="speak", description="แปลงข้อความเป็นเสียงพูด (ภาษาไทย)")
    @app_commands.describe(text="ข้อความที่ต้องการให้พูด")
    async def speak(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer(ephemeral=True)
        try:
            if len(text) > 200:
                await interaction.followup.send("ข้อความยาวเกินไป (สูงสุด 200 ตัวอักษร)", ephemeral=True)
                return
                
            voice_client = interaction.guild.voice_client
            if not voice_client:
                await interaction.followup.send("บอทต้องอยู่ในห้องเสียงก่อนถึงจะพูดได้", ephemeral=True)
                return
                
            if voice_client.is_playing():
                await interaction.followup.send("กำลังเล่นเพลงอยู่ ไม่สามารถพูดได้", ephemeral=True)
                return

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
                
                await interaction.followup.send(f"🗣️ กำลังพูด: '{text}'", ephemeral=False)
                
            except Exception as e:
                logger.error(f"TTS error: {e}")
                try:
                    os.unlink(speech_file)
                except:
                    pass
                await interaction.followup.send("ไม่สามารถสร้างเสียงพูดได้", ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error in speak command: {e}")
            await interaction.followup.send("ไม่สามารถทำงานได้", ephemeral=True)

    @app_commands.command(name="wake", description="ส่งข้อความส่วนตัวไปปลุกเพื่อน")
    @app_commands.describe(user="ผู้ใช้ที่ต้องการปลุก", message="ข้อความ (ไม่บังคับ)")
    async def wake(self, interaction: discord.Interaction, user: discord.Member, message: str = "ตื่นได้แล้ว!"):
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

async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))

