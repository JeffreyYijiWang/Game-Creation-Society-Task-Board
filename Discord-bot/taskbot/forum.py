from __future__ import annotations

import discord
from discord.ext import commands

from taskbot.config import settings
from taskbot.db import count_task_claimers
from taskbot.utils import split_tags
from taskbot.components_v2_all import task_message_kwargs, task_edit_kwargs, task_v2_title


def split_env_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]



def task_v2_title(task: dict) -> str:
    archive_prefix = "[ARCHIVED] " if task.get("archived") else ""
    claimed = count_task_claimers(task["id"])
    needed = int(task.get("positions_needed") or 1)
    filled = "[FILLED] " if claimed >= needed else ""
    roles = task.get("job_role") or "Role"
    return f"{archive_prefix}{filled}#{task['id']} [{roles}] {task['title']}"[:100]


def matching_forum_tags(forum: discord.ForumChannel, task: dict) -> list[discord.ForumTag]:
    claimed = count_task_claimers(task["id"])
    needed = int(task.get("positions_needed") or 1)
    environments = [x.strip() for x in str(task.get("dev_environment") or "").split(",") if x.strip()]
    roles = [x.strip() for x in str(task.get("job_role") or "").split(",") if x.strip()]
    task_types = [x.strip() for x in str(task.get("task_type") or "").split(",") if x.strip()]
    wanted_names = [
        "Filled" if claimed >= needed else task["status"],
        *task_types,
        *roles,
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
        await thread.edit(name=task_v2_title(task), applied_tags=matching_forum_tags(forum, task))
    except discord.HTTPException:
        pass
    if task.get("message_id"):
        try:
            starter_message = await thread.fetch_message(task["message_id"])
            await starter_message.edit(**task_edit_kwargs(task))
        except discord.HTTPException:
            pass
    try:
        await thread.edit(archived=bool(task.get("archived")), locked=bool(task.get("archived")))
    except discord.HTTPException:
        pass

# ---- v7 forum title override: no task id, bracketed tags ---------------------

def _taskbot_title_parts(task: dict) -> list[str]:
    parts: list[str] = []
    def add(value: object, max_len: int = 18) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        for item in text.replace("\n", ",").split(","):
            item = item.strip()
            if item and item not in parts:
                parts.append(item[:max_len])
    add(task.get("priority"), 10)
    add(task.get("job_role") or task.get("job_roles"), 18)
    add(task.get("dev_environment") or task.get("dev_environments"), 12)
    add(task.get("game_engine"), 12)
    try:
        from taskbot.db import get_claimers
        capacity = int(task.get("positions_needed") or task.get("claim_capacity") or 1)
        if len(get_claimers(int(task["id"]))) >= capacity:
            add("Filled", 10)
    except Exception:
        pass
    return parts[:4]


def task_v2_title(task: dict) -> str:
    title = str(task.get("title") or "Untitled Task").strip()
    parts = _taskbot_title_parts(task)
    prefix = f"[{' | '.join(parts)}] " if parts else ""
    return (prefix + title)[:100]

# Compatibility name for older imports/calls.
# The v2 implementation still uses bracketed tags and removes task ids.
def task_thread_title(task: dict) -> str:
    return task_v2_title(task)
