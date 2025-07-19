# bot/bot.py
import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# --- Initialization ---
# Load environment variables from .env file
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

# Initialize Firebase Admin SDK
# The service account key is stored securely as an environment variable
cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Define bot intents
# We need guilds to identify servers and voice_states to manage voice connections.
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.message_content = True # Required for potential future features

# Create the bot instance
# Using commands.Bot to support cogs and slash commands
bot = commands.Bot(command_prefix="/", intents=intents)

# --- Bot Events ---
@bot.event
async def on_ready():
    """
    Called when the bot successfully connects to Discord.
    It syncs the slash commands with Discord's API and prints a confirmation.
    """
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')
    try:
        # Sync all slash commands defined in the cogs to the command tree.
        # This makes them available in Discord.
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    # Start the Firebase listener in the background
    bot.loop.create_task(listen_for_web_commands())


async def listen_for_web_commands():
    """
    Listens to the 'commands' collection in Firestore for each guild the bot is in.
    This allows the web dashboard to send commands to the bot in real-time.
    """
    await bot.wait_until_ready()
    for guild in bot.guilds:
        # Create a snapshot listener for each guild's command collection
        collection_ref = db.collection('guilds').document(str(guild.id)).collection('commands')
        
        # The callback function `on_snapshot` will be triggered on any change
        collection_ref.on_snapshot(lambda docs, changes, read_time, guild_id=guild.id: on_command_snapshot(docs, changes, read_time, guild_id))
        print(f"Listening for web commands in guild: {guild.name} ({guild.id})")

def on_command_snapshot(doc_snapshot, changes, read_time, guild_id):
    """
    Callback function for the Firestore listener.
    Processes new commands added to the 'commands' collection.
    """
    for change in changes:
        if change.type.name == 'ADDED':
            command_data = change.document.to_dict()
            print(f"Received web command for guild {guild_id}: {command_data}")
            
            # Schedule the command execution in the bot's event loop
            asyncio.run_coroutine_threadsafe(
                handle_web_command(guild_id, command_data),
                bot.loop
            )
            
            # Delete the command document to prevent re-execution
            change.document.reference.delete()

async def handle_web_command(guild_id, command_data):
    """
    Executes a command received from the web dashboard by creating a mock Interaction.
    """
    action = command_data.get("action")
    payload = command_data.get("payload")
    requester_id = command_data.get("requester_id")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        return

    music_cog = bot.get_cog('Music')
    voice_cog = bot.get_cog('Voice')
    utility_cog = bot.get_cog('Utility')

    # Find a text channel to send feedback to. Fallback to system channel if no text channels.
    channel = guild.text_channels[0] if guild.text_channels else guild.system_channel
    if not channel:
        print(f"Error: No suitable channel in guild {guild.id} to send command feedback.")
        return

    requester = guild.get_member(int(requester_id))
    if not requester:
        print(f"Error: Cannot find requester {requester_id} in guild {guild.id}")
        return

    # --- Mock Interaction classes ---
    # This is required because app commands expect an 'Interaction' object,
    # not a 'Context' object. We simulate this object for web-based commands.
    class MockFollowup:
        def __init__(self, channel):
            self._channel = channel
        async def send(self, *args, **kwargs):
            return await self._channel.send(*args, **kwargs)

    class MockResponse:
        def __init__(self, interaction):
            self._interaction = interaction
            self._deffered = False
        async def defer(self, *args, **kwargs):
            self._deffered = True
        async def send_message(self, *args, **kwargs):
            return await self._interaction.channel.send(*args, **kwargs)

    class MockInteraction:
        def __init__(self, guild, channel, author):
            self.guild = guild
            self.channel = channel
            self.user = author
            self.voice_client = guild.voice_client
            self._response = MockResponse(self)
            self._followup = MockFollowup(channel)

        @property
        def response(self):
            return self._response
        
        @property
        def followup(self):
            return self._followup
            
        async def send(self, *args, **kwargs): # For compatibility if a command uses ctx.send
            await self.channel.send(*args, **kwargs)

    # Create the mock interaction object
    interaction = MockInteraction(guild, channel, requester)

    # --- Route command to the correct cog and method ---
    try:
        if action == "play" and music_cog:
            await music_cog.play(interaction, query=payload)
        elif action == "pause" and music_cog:
            await music_cog.pause(interaction)
        elif action == "resume" and music_cog:
            await music_cog.resume(interaction)
        elif action == "skip" and music_cog:
            await music_cog.skip(interaction)
        elif action == "stop" and music_cog:
            await music_cog.stop(interaction)
        # Add other commands as needed
    except Exception as e:
        print(f"Error handling web command '{action}' in guild {guild.id}: {e}")
        await channel.send(f"An error occurred while trying to execute the command from the web panel: `{e}`")


# --- Main Execution ---
async def main():
    """
    Main function to load cogs and start the bot.
    """
    # Load all cogs from the 'cogs' directory
    async with bot:
        for filename in os.listdir('./bot/cogs'):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    await bot.load_extension(f'cogs.{filename[:-3]}')
                    print(f"Loaded cog: {filename}")
                except Exception as e:
                    print(f"Failed to load cog {filename}: {e}")
        
        # Start the bot with the token from environment variables
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    # Run the main async function
    # This is the entry point when the script is executed.
    asyncio.run(main())
