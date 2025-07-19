# bot/cogs/utility.py
import discord
from discord.ext import commands
from discord import app_commands
import logging

class Utility(commands.Cog):
    """A cog for miscellaneous utility commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="wake", description="Sends a direct message to a user to get their attention.")
    @app_commands.describe(user="The user to wake up.")
    async def wake(self, interaction: discord.Interaction, user: discord.Member):
        """
        Sends a DM to the specified user. This is a simple way to ping someone
        privately. It includes error handling in case the user has DMs disabled.
        """
        if user.bot:
            await interaction.response.send_message("You can't wake up a bot!", ephemeral=True)
            return
        
        if user == interaction.user:
            await interaction.response.send_message("You can't wake yourself up! Silly.", ephemeral=True)
            return

        try:
            # Create a custom embed for the DM for a nicer look
            embed = discord.Embed(
                title="⏰ Wake Up!",
                description=f"Hey {user.mention}, **{interaction.user.display_name}** from the server **'{interaction.guild.name}'** needs your attention!",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text=f"Sent from #{interaction.channel.name}")
            
            await user.send(embed=embed)
            await interaction.response.send_message(f"Sent a wake-up call to {user.mention}.", ephemeral=True)
        except discord.Forbidden:
            # This error occurs if the bot cannot DM the user (e.g., privacy settings)
            await interaction.response.send_message(f"Could not send a DM to {user.mention}. They might have DMs disabled or have blocked me.", ephemeral=True)
        except Exception as e:
            # Catch any other potential errors
            logging.error(f"Failed to send wake-up DM from {interaction.user.id} to {user.id}: {e}")
            await interaction.response.send_message(f"An unexpected error occurred: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
