
import discord
from discord.ext import commands
from discord import app_commands

class Management(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sync", description="Sync commands with Discord")
    @commands.is_owner()
    async def sync(self, interaction: discord.Interaction):
        try:
            synced = await self.bot.tree.sync()
            await interaction.response.send_message(f"Synced {len(synced)} commands.")
        except Exception as e:
            await interaction.response.send_message(f"Failed to sync commands: {e}")

    @app_commands.command(name="load", description="Load a cog")
    @commands.is_owner()
    async def load(self, interaction: discord.Interaction, cog: str):
        try:
            await self.bot.load_extension(f"cogs.{cog}")
            await interaction.response.send_message(f"Loaded cog: {cog}")
        except Exception as e:
            await interaction.response.send_message(f"Failed to load cog: {e}")

    @app_commands.command(name="unload", description="Unload a cog")
    @commands.is_owner()
    async def unload(self, interaction: discord.Interaction, cog: str):
        try:
            await self.bot.unload_extension(f"cogs.{cog}")
            await interaction.response.send_message(f"Unloaded cog: {cog}")
        except Exception as e:
            await interaction.response.send_message(f"Failed to unload cog: {e}")

    @app_commands.command(name="reload", description="Reload a cog")
    @commands.is_owner()
    async def reload(self, interaction: discord.Interaction, cog: str):
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await interaction.response.send_message(f"Reloaded cog: {cog}")
        except Exception as e:
            await interaction.response.send_message(f"Failed to reload cog: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Management(bot))
