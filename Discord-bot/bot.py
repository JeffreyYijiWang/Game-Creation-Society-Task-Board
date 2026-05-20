from __future__ import annotations

import logging

import discord
from discord.ext import commands

from taskbot.config import settings
from taskbot.constants import JOB_ROLE_EMOJIS
from taskbot.db import get_config, init_db, subscribe_user_to_role, unsubscribe_user_from_role
from taskbot.views import TaskControls
from taskbot.commands import setup_commands
from taskbot.reminders import ReminderCog


class KanbanBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.reactions = True
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


    async def _handle_subscription_reaction(self, payload: discord.RawReactionActionEvent, *, adding: bool) -> None:
        if payload.guild_id is None or payload.user_id == (self.user.id if self.user else None):
            return
        info_page_id = get_config(payload.guild_id, "info_page_message_id")
        if not info_page_id or str(payload.message_id) != str(info_page_id):
            return
        emoji = str(payload.emoji)
        role = next((name for name, role_emoji in JOB_ROLE_EMOJIS.items() if role_emoji == emoji), None)
        if not role:
            return
        if adding:
            subscribe_user_to_role(payload.guild_id, payload.user_id, role)
        else:
            unsubscribe_user_from_role(payload.guild_id, payload.user_id, role)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._handle_subscription_reaction(payload, adding=True)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._handle_subscription_reaction(payload, adding=False)

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
