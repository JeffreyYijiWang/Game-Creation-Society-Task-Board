from __future__ import annotations

import discord

from taskbot.config import settings
from taskbot.constants import STATUS_COLORS
from taskbot.db import count_task_claimers, get_attachments, get_claimers
from taskbot.utils import engine_label, format_user


def task_embed(task: dict) -> discord.Embed:
    status = task["status"]
    due_date = task.get("due_date") or "No due date"
    tags = task.get("tags") or "None"
    resource_links = task.get("resource_links") or "None"
    needed = int(task.get("positions_needed") or 1)
    claimed_count = count_task_claimers(task["id"])
    claimers = get_claimers(task["id"])

    embed = discord.Embed(
        title=f"Task #{task['id']}: {task['title']}",
        description=task.get("description") or "No description provided.",
        color=STATUS_COLORS.get(status, discord.Color.blurple()),
    )
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Priority", value=task["priority"], inline=True)
    embed.add_field(name="Openings", value=f"{claimed_count} / {needed} claimed", inline=True)
    embed.add_field(name="Job Role", value=task.get("job_role") or "Not specified", inline=True)
    embed.add_field(name="Dev Environments", value=task.get("dev_environment") or "Not specified", inline=True)
    embed.add_field(name="Game Engine", value=engine_label(task), inline=True)
    embed.add_field(name="Due Date", value=due_date, inline=True)
    embed.add_field(name="Created By", value=format_user(task["creator_id"]), inline=True)
    embed.add_field(name="Claimers", value=", ".join(format_user(uid) for uid in claimers) if claimers else "No one yet", inline=False)
    embed.add_field(name="Tags", value=tags, inline=False)
    embed.add_field(name="Links / Resources", value=resource_links[:1024], inline=False)

    attachments = get_attachments(task["id"], limit=10)
    if attachments:
        lines = []
        for item in attachments:
            note = f" — {item['notes']}" if item.get("notes") else ""
            lines.append(f"[{item['filename']}]({item['url']}){note}")
        embed.add_field(name="Recent Attachments", value="\n".join(lines)[:1024], inline=False)

    if task.get("thumbnail_url"):
        embed.set_image(url=task["thumbnail_url"])
    if claimed_count >= needed:
        embed.add_field(name="Filled", value="This post has enough claimers.", inline=False)
    embed.set_footer(text=f"Updated: {task['updated_at']}")
    return embed


def profile_embed(user: discord.abc.User, stats: dict, max_active: int, profile: dict | None = None) -> discord.Embed:
    profile = profile or {}
    display_name = profile.get("display_name") or user.display_name
    embed = discord.Embed(
        title=f"Task Profile: {display_name}",
        description=profile.get("bio") or "No profile bio yet. Use `/task edit_profile` to add one.",
        color=discord.Color.blurple(),
    )
    image_url = profile.get("profile_image_url") or user.display_avatar.url
    embed.set_thumbnail(url=image_url)
    embed.add_field(name="Skills", value=profile.get("skills") or "Not set", inline=False)
    embed.add_field(name="Preferred Roles", value=profile.get("preferred_roles") or "Not set", inline=True)
    embed.add_field(name="Dev Environments", value=profile.get("dev_environments") or "Not set", inline=True)
    embed.add_field(name="Availability", value=profile.get("availability") or "Not set", inline=False)
    if profile.get("portfolio_url"):
        embed.add_field(name="Portfolio", value=profile["portfolio_url"], inline=False)
    embed.add_field(name="Active Claimed", value=f"{stats['active_claimed']} / {max_active}", inline=True)
    embed.add_field(name="Completed", value=str(stats["completed"]), inline=True)
    embed.add_field(name="Created Active", value=str(stats["created_active"]), inline=True)
    embed.add_field(name="Created Archived", value=str(stats["created_archived"]), inline=True)
    return embed


def template_embed(template: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"Template: {template['name']}",
        description=template.get("description") or "No description.",
        color=discord.Color.purple(),
    )
    embed.add_field(name="Title", value=template.get("title") or "Untitled", inline=False)
    embed.add_field(name="Priority", value=template.get("priority") or "Medium", inline=True)
    embed.add_field(name="Openings", value=str(template.get("positions_needed") or 1), inline=True)
    embed.add_field(name="Job Role", value=template.get("job_role") or "Programmer", inline=True)
    embed.add_field(name="Dev Environments", value=template.get("dev_environment") or "Windows", inline=True)
    embed.add_field(name="Game Engine", value=template.get("game_engine") or "Unity", inline=True)
    embed.add_field(name="Custom Engine", value=template.get("custom_game_engine") or "None", inline=True)
    embed.add_field(name="Tags", value=template.get("tags") or "None", inline=False)
    embed.add_field(name="Links", value=(template.get("resource_links") or "None")[:1024], inline=False)
    if template.get("thumbnail_url"):
        embed.set_image(url=template["thumbnail_url"])
    return embed


def dashboard_embed(user: discord.abc.User, tasks: list[dict], include_archived: bool) -> discord.Embed:
    embed = discord.Embed(
        title=f"Task-assigner dashboard for {user.display_name}",
        description="Tasks you created. Archive filled posts when you no longer need more people.",
        color=discord.Color.gold(),
    )
    if not tasks:
        embed.add_field(name="No tasks found", value="You do not have matching created tasks.", inline=False)
        return embed
    lines = []
    for task in tasks:
        thread = f"<#{task['thread_id']}>" if task.get("thread_id") else "No thread"
        archived = " archived" if task.get("archived") else ""
        claimed = count_task_claimers(task["id"])
        needed = int(task.get("positions_needed") or 1)
        fill = "FULL" if claimed >= needed else "OPEN"
        lines.append(f"**#{task['id']}** {thread} — **{task['status']}** — {fill} {claimed}/{needed} — {task.get('job_role')}{archived}\n{task['title']}")
    embed.add_field(name="Created Tasks" + (" including archived" if include_archived else ""), value="\n\n".join(lines)[:4096], inline=False)
    return embed


def command_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Discord Kanban / Recruitment Bot Commands",
        description="Create, claim, filter, archive, template, and track Discord-native task posts.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="/task create", value="Open the create wizard with dropdowns, multi-select dev environments, and optional thumbnail.", inline=False)
    embed.add_field(name="/task attach", value="Attach up to 5 images/documents/files to an existing task.", inline=False)
    embed.add_field(name="/task claim / assign", value="Claim a post or assign a member. Sends the worker's task profile to the assigner.", inline=False)
    embed.add_field(name="/task edit_profile / profile / send_profile", value="Edit your task profile card, view projects, or send the card to a task assigner.", inline=False)
    embed.add_field(name="/task move / done", value="Move status or mark done.", inline=False)
    embed.add_field(name="/task archive / restore", value="Remove from active board while keeping it stored, or restore later.", inline=False)
    embed.add_field(name="/task search", value="Search by status, priority, tag, claimer, creator, role, OS, or engine.", inline=False)
    embed.add_field(name="/task dashboard", value=f"For `{settings.task_assigner_role}` users: see posts you created and whether they are filled.", inline=False)
    embed.add_field(name="/template save / edit / use / view / list / delete", value="Save reusable task forms, display them as cards, and edit through buttons/modals.", inline=False)
    return embed
