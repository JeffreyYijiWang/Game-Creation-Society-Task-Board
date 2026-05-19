from __future__ import annotations

import discord
from discord.ext import commands

from taskbot.config import settings
from taskbot.db import get_claimers, get_profile, get_profile_stats, update_task
from taskbot.embeds import profile_embed
from taskbot.forum import fetch_task_thread
from taskbot.views import ProfileCardView


async def safe_dm(user: discord.abc.User | None, content: str | None = None, *, embed: discord.Embed | None = None, view: discord.ui.View | None = None) -> bool:
    if user is None:
        return False
    try:
        await user.send(content=content, embed=embed, view=view)
        return True
    except discord.HTTPException:
        return False


async def get_or_create_claim_thread(bot: commands.Bot, task: dict) -> discord.Thread | None:
    if task.get("claim_thread_id"):
        existing = await fetch_task_thread(bot, task.get("claim_thread_id"))
        if existing:
            return existing
    if not settings.claim_discussion_channel_id:
        return await fetch_task_thread(bot, task.get("thread_id"))
    parent = bot.get_channel(settings.claim_discussion_channel_id)
    if parent is None:
        try:
            parent = await bot.fetch_channel(settings.claim_discussion_channel_id)
        except discord.HTTPException:
            return await fetch_task_thread(bot, task.get("thread_id"))
    if not isinstance(parent, discord.TextChannel):
        return await fetch_task_thread(bot, task.get("thread_id"))
    message = await parent.send(f"Coordination space for task **#{task['id']} — {task['title']}**")
    thread = await message.create_thread(name=f"Task #{task['id']} coordination", auto_archive_duration=10080)
    update_task(task["id"], task["creator_id"], "claim_thread_created", claim_thread_id=thread.id)
    return thread


async def notify_claim(bot: commands.Bot, task: dict, claimer: discord.abc.User) -> None:
    creator = await bot.fetch_user(task["creator_id"])
    original_thread = await fetch_task_thread(bot, task.get("thread_id"))
    coordination_thread = await get_or_create_claim_thread(bot, task)
    task_link = original_thread.mention if original_thread else f"Task #{task['id']}"
    coord_link = coordination_thread.mention if coordination_thread else task_link

    await safe_dm(
        creator,
        f"{claimer.mention} claimed your task **#{task['id']} — {task['title']}**. Task: {task_link}\nCoordination: {coord_link}\nTheir task profile card is below.",
    )
    await safe_dm(
        claimer,
        f"You claimed **#{task['id']} — {task['title']}** created by {creator.mention}. Task: {task_link}\nCoordination: {coord_link}",
    )

    guild_id = int(task["guild_id"])
    stats = get_profile_stats(claimer.id, guild_id)
    profile = get_profile(guild_id, claimer.id)
    card = profile_embed(claimer, stats, settings.max_active_assignments, profile)
    profile_view = ProfileCardView(claimer.id, guild_id)
    await safe_dm(creator, embed=card, view=profile_view)

    if coordination_thread:
        claimers = " ".join(f"<@{uid}>" for uid in get_claimers(task["id"]))
        await coordination_thread.send(f"{creator.mention} {claimer.mention} — new claim added.\nCurrent claimers: {claimers or 'none'}")
        await coordination_thread.send(f"Task profile for {claimer.mention}:", embed=card, view=ProfileCardView(claimer.id, guild_id))


async def send_due_reminder(bot: commands.Bot, task: dict) -> None:
    thread = await fetch_task_thread(bot, task.get("thread_id"))
    creator = await bot.fetch_user(task["creator_id"])
    claimers = get_claimers(task["id"])
    users = [await bot.fetch_user(uid) for uid in claimers] if claimers else [creator]
    task_link = thread.mention if thread else f"Task #{task['id']}"
    message = f"Reminder: **#{task['id']} — {task['title']}** is due tomorrow ({task.get('due_date')}). Open: {task_link}"
    for user in users:
        await safe_dm(user, message)
    if thread:
        mentions = " ".join(user.mention for user in users)
        await thread.send(f"{mentions} {message}")
