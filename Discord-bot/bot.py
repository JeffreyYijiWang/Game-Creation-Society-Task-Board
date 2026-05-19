from __future__ import annotations

import logging

import discord
from discord.ext import commands

from taskbot.config import settings
from taskbot.db import init_db
from taskbot.views import TaskControls
from taskbot.commands import setup_commands
from taskbot.reminders import ReminderCog


class KanbanBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        # message_content is not required for slash commands, but useful if you later add prefix fallback commands.
        intents.message_content = False

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        init_db()
        self.add_view(TaskControls())  # persistent buttons after restart

        setup_commands(self)
        await self.add_cog(ReminderCog(self))

        if settings.guild_id:
            guild = discord.Object(id=settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Synced slash commands to guild {settings.guild_id}")
        else:
            await self.tree.sync()
            print("Synced slash commands globally. Global sync can take time to appear.")

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user} (ID: {self.user.id if self.user else 'unknown'})")


if __name__ == "__main__":
    if not settings.discord_token:
        raise RuntimeError("Missing DISCORD_TOKEN in .env")
    if not settings.task_forum_channel_id:
        raise RuntimeError("Missing TASK_FORUM_CHANNEL_ID in .env")

    handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
    bot = KanbanBot()
    bot.run(settings.discord_token, log_handler=handler, log_level=logging.INFO)
