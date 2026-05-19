from __future__ import annotations

import discord
from discord.ext import commands

from taskbot.config import settings
from taskbot.db import count_task_claimers
from taskbot.utils import split_tags


def task_thread_title(task: dict) -> str:
    archive_prefix = "[ARCHIVED] " if task.get("archived") else ""
    claimed = count_task_claimers(task["id"])
    needed = int(task.get("positions_needed") or 1)
    filled = "[FILLED] " if claimed >= needed else ""
    return f"{archive_prefix}{filled}#{task['id']} [{task.get('job_role')}] {task['title']}"[:100]


def matching_forum_tags(forum: discord.ForumChannel, task: dict) -> list[discord.ForumTag]:
    claimed = count_task_claimers(task["id"])
    needed = int(task.get("positions_needed") or 1)
    environments = [x.strip() for x in str(task.get("dev_environment") or "").split(",") if x.strip()]
    wanted_names = [
        "Filled" if claimed >= needed else task["status"],
        task.get("job_role") or "",
        f"Need {needed}",
        *environments,
        task.get("game_engine") or "",
        task.get("priority") or "",
        *split_tags(task.get("tags")),
    ]
    by_name = {tag.name.lower(): tag for tag in forum.available_tags}
    result: list[discord.ForumTag] = []
    seen: set[int] = set()
    for name in wanted_names:
        if not name:
            continue
        forum_tag = by_name.get(str(name).lower())
        if forum_tag and forum_tag.id not in seen:
            seen.add(forum_tag.id)
            result.append(forum_tag)
        if len(result) >= 5:
            break
    return result


async def get_task_forum(bot: commands.Bot) -> discord.ForumChannel:
    channel = bot.get_channel(settings.task_forum_channel_id)
    if channel is None:
        channel = await bot.fetch_channel(settings.task_forum_channel_id)
    if not isinstance(channel, discord.ForumChannel):
        raise RuntimeError("TASK_FORUM_CHANNEL_ID must point to a Discord Forum Channel.")
    return channel


async def fetch_task_thread(bot: commands.Bot, thread_id: int | None) -> discord.Thread | None:
    if not thread_id:
        return None
    channel = bot.get_channel(thread_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(thread_id)
        except discord.HTTPException:
            return None
    return channel if isinstance(channel, discord.Thread) else None


async def sync_discord_task(bot: commands.Bot, task: dict) -> None:
    if not task.get("thread_id"):
        return
    from taskbot.embeds import task_embed
    from taskbot.views import TaskControls
    forum = await get_task_forum(bot)
    thread = await fetch_task_thread(bot, task.get("thread_id"))
    if not thread:
        return
    try:
        await thread.edit(name=task_thread_title(task), applied_tags=matching_forum_tags(forum, task))
    except discord.HTTPException:
        pass
    if task.get("message_id"):
        try:
            starter_message = await thread.fetch_message(task["message_id"])
            await starter_message.edit(embed=task_embed(task), view=TaskControls())
        except discord.HTTPException:
            pass
    try:
        await thread.edit(archived=bool(task.get("archived")), locked=bool(task.get("archived")))
    except discord.HTTPException:
        pass
