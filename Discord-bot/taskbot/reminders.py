from __future__ import annotations

import datetime

from discord.ext import commands, tasks

from taskbot.config import settings
from taskbot.db import mark_reminder_sent, tasks_due_tomorrow
from taskbot.notifications import send_due_reminder


class ReminderCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.due_date_reminders.start()

    def cog_unload(self) -> None:
        self.due_date_reminders.cancel()

    @tasks.loop(minutes=60)
    async def due_date_reminders(self) -> None:
        for task in tasks_due_tomorrow():
            try:
                await send_due_reminder(self.bot, task)
                mark_reminder_sent(task["id"], "due_day_before")
            except Exception as exc:
                print(f"Reminder failed for task #{task.get('id')}: {exc}")

    @due_date_reminders.before_loop
    async def before_due_date_reminders(self) -> None:
        await self.bot.wait_until_ready()
