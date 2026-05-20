from __future__ import annotations

import discord

from taskbot.config import settings
from taskbot.constants import JOB_ROLE_EMOJIS, JOB_ROLES, STATUS_COLORS
from taskbot.db import count_task_claimers, get_attachments, get_claimers
from taskbot.utils import engine_label, format_user, today_local


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
    embed.add_field(name="Task Type", value=task.get("task_type") or "Feature", inline=True)
    embed.add_field(name="Job Roles", value=task.get("job_role") or "Not specified", inline=True)
    embed.add_field(name="Dev Environments", value=task.get("dev_environment") or "Not specified", inline=True)
    embed.add_field(name="Game Engine", value=engine_label(task), inline=True)
    if task.get("game_programs"):
        embed.add_field(name="Programs / Tools Familiarity", value=task.get("game_programs") or "None", inline=False)
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
    embed.add_field(name="Programs / Tools", value=profile.get("game_programs") or "Not set", inline=False)
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
    embed.add_field(name="Task Type", value=template.get("task_type") or "Feature", inline=True)
    embed.add_field(name="Job Roles", value=template.get("job_role") or "Programmer", inline=True)
    embed.add_field(name="Dev Environments", value=template.get("dev_environment") or "Windows", inline=True)
    embed.add_field(name="Game Engine", value=template.get("game_engine") or "Unity", inline=True)
    embed.add_field(name="Custom Engine", value=template.get("custom_game_engine") or "None", inline=True)
    embed.add_field(name="Programs / Tools", value=template.get("game_programs") or "None", inline=False)
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


def _short_task_line(task: dict) -> str:
    thread = f"<#{task['thread_id']}>" if task.get("thread_id") else "No thread"
    claimed = count_task_claimers(task["id"])
    needed = int(task.get("positions_needed") or 1)
    due = f" — due {task.get('due_date')}" if task.get("due_date") else ""
    archived = " — archived" if task.get("archived") else ""
    return (
        f"**#{task['id']}** {thread} — {claimed}/{needed}{due}{archived}\n"
        f"{str(task.get('title') or 'Untitled')[:90]}"
    )


def _is_late(task: dict) -> bool:
    due_date = str(task.get("due_date") or "").strip()
    if not due_date or task.get("archived") or task.get("status") in {"Done", "Archived"}:
        return False
    return due_date < today_local().isoformat()


def _bucket_dashboard_tasks(tasks: list[dict], *, show_closed: bool) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {
        "To Do": [],
        "In Progress": [],
        "Review": [],
        "Late": [],
        "Done": [],
        "Archived": [],
    }
    for task in tasks:
        status = str(task.get("status") or "To Do")
        if task.get("archived") or status == "Archived":
            if show_closed:
                buckets["Archived"].append(task)
            continue
        if status == "Done":
            if show_closed:
                buckets["Done"].append(task)
            continue
        if _is_late(task):
            buckets["Late"].append(task)
        elif status in buckets:
            buckets[status].append(task)
        else:
            buckets["To Do"].append(task)
    return buckets


def _field_value(tasks: list[dict], empty: str = "None") -> str:
    if not tasks:
        return empty
    return "\n\n".join(_short_task_line(task) for task in tasks)[:1024]


def _add_kanban_fields(embed: discord.Embed, tasks: list[dict], *, show_closed: bool, horizontal: bool) -> None:
    buckets = _bucket_dashboard_tasks(tasks, show_closed=show_closed)
    open_names = ["To Do", "In Progress", "Review", "Late"]
    if horizontal:
        for name in open_names:
            embed.add_field(name=f"{name} ({len(buckets[name])})", value=_field_value(buckets[name]), inline=True)
        if show_closed:
            embed.add_field(name=f"Done ({len(buckets['Done'])})", value=_field_value(buckets["Done"]), inline=True)
            embed.add_field(name=f"Archived ({len(buckets['Archived'])})", value=_field_value(buckets["Archived"]), inline=True)
    else:
        names = open_names + (["Done", "Archived"] if show_closed else [])
        for name in names:
            embed.add_field(name=f"{name} ({len(buckets[name])})", value=_field_value(buckets[name]), inline=False)


def _add_assigner_list(embed: discord.Embed, tasks: list[dict], *, show_closed: bool) -> None:
    visible: list[dict] = []
    hidden = 0
    for task in tasks:
        is_closed = bool(task.get("archived")) or task.get("status") in {"Done", "Archived"}
        if is_closed and not show_closed:
            hidden += 1
            continue
        visible.append(task)

    if not visible:
        extra = f" {hidden} done/archived task(s) hidden." if hidden else ""
        embed.add_field(name="Created Tasks", value=f"No matching visible tasks.{extra}", inline=False)
        return

    lines = []
    for task in visible[:25]:
        claimed = count_task_claimers(task["id"])
        needed = int(task.get("positions_needed") or 1)
        fill = "FULL" if claimed >= needed else "OPEN"
        lines.append(
            f"**#{task['id']}** <#{task['thread_id']}> — **{task.get('status')}** — {fill} {claimed}/{needed} — {task.get('job_role')}\n"
            f"{task.get('title') or 'Untitled'}"
        )
    if hidden:
        lines.append(f"*{hidden} done/archived task(s) hidden. Press **Show Done + Archived** to reveal them.*")
    embed.add_field(name="Created Tasks", value="\n\n".join(lines)[:4096], inline=False)


def dashboard_board_embed(
    user: discord.abc.User,
    personal_tasks: list[dict],
    assigner_tasks: list[dict],
    *,
    is_assigner_user: bool,
    mode: str = "personal_horizontal",
    show_closed: bool = False,
) -> discord.Embed:
    mode_titles = {
        "personal_horizontal": "Personal Task Board — horizontal",
        "personal_vertical": "Personal Task Board — vertical",
        "assigner_list": "Task-assigner Dashboard — list",
        "assigner_horizontal": "Task-assigner Kanban — horizontal",
        "assigner_vertical": "Task-assigner Kanban — vertical",
    }
    embed = discord.Embed(
        title=f"{mode_titles.get(mode, 'Task Dashboard')} for {user.display_name}",
        description=(
            "Open columns show active work. Late means the due date has passed and the task is not done/archived. "
            "Done and archived tasks stay hidden until you press **Show Done + Archived**."
        ),
        color=discord.Color.gold() if mode.startswith("assigner") else discord.Color.blurple(),
    )

    if mode.startswith("assigner"):
        if not is_assigner_user:
            embed.add_field(name="Task-assigner access", value="You do not have task-assigner access, so only the personal board is available.", inline=False)
            _add_kanban_fields(embed, personal_tasks, show_closed=show_closed, horizontal=True)
            return embed
        if mode == "assigner_list":
            _add_assigner_list(embed, assigner_tasks, show_closed=show_closed)
        else:
            _add_kanban_fields(embed, assigner_tasks, show_closed=show_closed, horizontal=(mode == "assigner_horizontal"))
    else:
        _add_kanban_fields(embed, personal_tasks, show_closed=show_closed, horizontal=(mode == "personal_horizontal"))

    embed.set_footer(text="Use the buttons below to switch personal/assigner, horizontal/vertical, and closed-task visibility.")
    return embed


def command_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Discord Kanban / Recruitment Bot Commands",
        description="Create, claim, filter, archive, template, and track Discord-native task posts.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="/task create", value="Open the create wizard with multi-select job roles, multi-select dev environments, capacity, engine, and optional thumbnail.", inline=False)
    embed.add_field(name="/task attach", value="Attach up to 5 images/documents/files to an existing task.", inline=False)
    embed.add_field(name="/task claim / assign", value="Claim a post or assign a member. Sends the worker's task profile to the assigner.", inline=False)
    embed.add_field(name="/task edit_profile / profile / send_profile", value="Edit your task profile card, view projects, or send the card to a task assigner.", inline=False)
    embed.add_field(name="/task edit / move / done / set_due", value="Admins can edit any task. Task assigners can edit tasks they created.", inline=False)
    embed.add_field(name="/task archive / restore", value="Remove from active board while keeping it stored, or restore later.", inline=False)
    embed.add_field(name="/task search", value="Search by status, priority, task type, creator, role, OS, engine, or optional custom tags. The role/OS/engine/type fields accept comma-separated multi-answer searches.", inline=False)
    embed.add_field(name="/task dashboard", value=f"For `{settings.task_assigner_role}` users: see posts you created and whether they are filled.", inline=False)
    embed.add_field(name="/task info_page / webhook_publish", value="Admins can publish the reaction-subscription info page or mirror a task to configured webhook board channels.", inline=False)
    embed.add_field(name="/template save / edit / use / view / list / delete", value="Save reusable task forms, display them as cards, and edit through buttons/modals.", inline=False)
    return embed



def create_guidance_embed(stage: str = "main") -> discord.Embed:
    title = "Task Create Guide — Step 1: roles, capacity, platform, type" if stage == "main" else "Task Create Guide — Step 2: engine, tools, form text"
    embed = discord.Embed(
        title=title,
        description="The dropdown values become searchable forum tags/dividers. After the dropdowns, the modal handles the written title, description, due date, links, tools, and optional custom tags.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Job roles", value="Choose one or more roles needed for the task. People can subscribe to these roles for new-task alerts.", inline=False)
    embed.add_field(name="People needed", value="The claim limit. Once this many people claim the task, it is marked filled.", inline=False)
    embed.add_field(name="Dev environments", value="Choose all supported platforms: Windows, Mac, Linux.", inline=False)
    embed.add_field(name="Task type", value="Use the type dropdown instead of free-text tags for major dividers: Bug Fix, Feature, Code, Art, 2D, 3D, UI, Research, Writing, Sound.", inline=False)
    embed.add_field(name="Game engine / tools", value="Pick the primary engine on step 2. In the modal, separate tools/programs with commas after `programs:`.", inline=False)
    embed.add_field(name="Links and custom tags", value="In the modal, separate links with commas or new lines after `links:`. Use `custom_tags:` only for extra labels that are not covered by the type dropdown.", inline=False)
    return embed


def info_page_embed() -> discord.Embed:
    embed = discord.Embed(
        title="How to Use the Discord Task Board",
        description="Create tasks in the task command channel, claim work from forum posts, and subscribe to role notifications with reactions below.",
        color=discord.Color.green(),
    )
    embed.add_field(name="Create", value="Task assigners use `/task create` or `/template use` to make a task post.", inline=False)
    embed.add_field(name="Claim", value="Open a task post and press **Claim**. Complete your `/task edit_profile` card before claiming so assigners can review your background.", inline=False)
    embed.add_field(name="Search", value="Use `/task search` by role, task type, engine, OS, priority, creator, or custom tag. Role/OS/engine/type searches accept comma-separated values.", inline=False)
    embed.add_field(name="Subscribe", value="React with a role emoji to get a DM when new tasks for that role are posted. Remove the reaction to unsubscribe.", inline=False)
    emoji_lines = [f"{JOB_ROLE_EMOJIS[role]} — {role}" for role in JOB_ROLES]
    embed.add_field(name="Role notification reactions", value="\n".join(emoji_lines), inline=False)
    return embed
