
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Mock discord.py classes and functions
class MockBot(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = AsyncMock()
        self.cogs = {}

    async def load_extension(self, name):
        self.cogs[name] = True

    async def unload_extension(self, name):
        if name in self.cogs:
            del self.cogs[name]

    async def reload_extension(self, name):
        await self.unload_extension(name)
        await self.load_extension(name)

@pytest.fixture
def bot():
    return MockBot()

@pytest.mark.asyncio
async def test_load_all_cogs(bot):
    import os
    cogs_dir = 'cogs'
    for filename in os.listdir(cogs_dir):
        if filename.endswith('.py') and not filename.startswith('__'):
            cog_name = f'cogs.{filename[:-3]}'
            await bot.load_extension(cog_name)
            assert cog_name in bot.cogs

@pytest.mark.asyncio
@pytest.mark.parametrize("cog_name", ["management", "music", "utility"])
async def test_reload_cog(bot, cog_name):
    cog_path = f"cogs.{cog_name}"
    await bot.load_extension(cog_path)
    assert cog_path in bot.cogs
    await bot.reload_extension(cog_path)
    assert cog_path in bot.cogs

