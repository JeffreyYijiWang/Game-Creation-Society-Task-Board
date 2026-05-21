from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from taskbot.access import can_manage_task, is_admin_member, is_task_assigner
from taskbot.config import settings
from taskbot.create_flow import TaskCreateSetupView, create_setup_embed, CreateTaskState
from taskbot.constants import GAME_ENGINES, JOB_ROLE_EMOJIS, JOB_ROLES, POSITIONS_NEEDED_CHOICES, PRIORITY_CHOICES, STATUS_CHOICES
from taskbot.db import (
    create_task_record,
    add_attachment,
    claim_task,
    count_active_assignments,
    delete_template,
    get_profile,
    get_profile_stats,
    get_task,
    get_config,
    get_template,
    list_templates,
    search_tasks,
    set_config,
    subscribe_user_to_role,
    unsubscribe_user_from_role,
    update_task,
)
from taskbot.embeds import template_detail_embed, template_list_embed, command_help_embed, create_guidance_embed, dashboard_board_embed, info_page_embed, profile_embed, task_embed, template_embed
from taskbot.forum import fetch_task_thread, get_task_forum, matching_forum_tags, task_thread_title, sync_discord_task
from taskbot.modals import ProfileEditModal, TaskCreateModal, TaskEditModal, TemplateSaveModal
from taskbot.notifications import notify_claim
from taskbot.utils import normalize_dev_environments, parse_due_date_to_iso
from taskbot.views import DashboardView, ProfileCardView, TaskCreateWizardView, TemplateDetailView, TemplateListView, template_list_content
from taskbot.template_edit_flow import TemplateEditStepOneView, template_edit_setup_embed
from taskbot.components_v2 import generic_message_kwargs, generic_edit_kwargs
from taskbot.components_v2_all import generic_message_kwargs, generic_edit_kwargs, v2_demo_kwargs, task_message_kwargs, task_message_kwargs

# ---- v10 search option helpers ---------------------------------------------

try:
    from discord import app_commands as _taskbot_app_commands
except Exception:  # pragma: no cover
    _taskbot_app_commands = None

try:
    from taskbot.constants import JOB_ROLES as _TASKBOT_JOB_ROLES
except Exception:
    _TASKBOT_JOB_ROLES = [
        "Programmer", "2D Artist", "UI Artist", "Writer", "SFX", "VFX",
        "Music Composer", "3D Artist", "3D Modeler", "Rigging",
        "3D Animator", "2D Animator", "Playtester",
    ]

try:
    from taskbot.constants import GAME_ENGINES as _TASKBOT_GAME_ENGINES
except Exception:
    _TASKBOT_GAME_ENGINES = ["Unity", "Unreal", "Godot", "Other"]

try:
    from taskbot.constants import DEV_ENVIRONMENTS as _TASKBOT_OS_OPTIONS
except Exception:
    _TASKBOT_OS_OPTIONS = ["Windows", "macOS", "Linux"]

try:
    from taskbot.constants import TASK_TYPES as _TASKBOT_TAG_OPTIONS
except Exception:
    _TASKBOT_TAG_OPTIONS = ["Bug Fix", "Feature", "Code", "Art", "2D", "3D", "UI", "Research", "Writing", "Sound"]


def _taskbot_choices(values):
    if _taskbot_app_commands is None:
        return []
    result = []
    seen = set()
    for value in values:
        label = str(value).strip()
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        result.append(_taskbot_app_commands.Choice(name=label[:100], value=label[:100]))
        if len(result) >= 25:
            break
    return result



async def command_channel_allowed(interaction: discord.Interaction) -> bool:
    allowed = settings.command_channel_ids
    if not allowed or interaction.channel_id in allowed:
        return True
    allowed_mentions = ", ".join(f"<#{cid}>" for cid in allowed)
    await interaction.response.send_message(f"Use this bot in the configured task command channel(s): {allowed_mentions}", ephemeral=True)
    return False


class GuardedGroup(app_commands.Group):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await command_channel_allowed(interaction)


task_group = GuardedGroup(name="task", description="Discord-native Kanban/recruitment task commands")
template_group = GuardedGroup(name="template", description="Save and reuse task post templates")


def setup_commands(bot: commands.Bot) -> None:
    bot.tree.add_command(task_group)
    bot.tree.add_command(template_group)


def member_has_task_assigner_role(member: discord.Member) -> bool:
    return is_task_assigner(member)


async def publish_template_as_task_now(interaction: discord.Interaction, template: dict) -> None:
    if not interaction.guild:
        await interaction.followup.send("Templates can only publish inside a server.", ephemeral=True)
        return

    forum = await get_task_forum(interaction.client)  # type: ignore[arg-type]
    title = template.get("title") or template.get("name") or "Untitled task"

    task = create_task_record(
        guild_id=interaction.guild.id,
        forum_channel_id=forum.id,
        title=title,
        description=template.get("description") or "",
        priority=template.get("priority") or "Medium",
        creator_id=interaction.user.id,
        due_date=template.get("due_date") or "",
        tags=template.get("tags") or "",
        resource_links=template.get("resource_links") or "",
        thumbnail_url=template.get("thumbnail_url") or "",
        positions_needed=int(template.get("positions_needed") or 1),
        job_role=template.get("job_role") or "Programmer",
        dev_environment=template.get("dev_environment") or template.get("dev_environments") or "Windows",
        game_engine=template.get("game_engine") or "Unity",
        custom_game_engine=template.get("custom_game_engine") or "",
    )

    created = await forum.create_thread(
        name=task_thread_title(task),
        applied_tags=matching_forum_tags(forum, task),
        **task_message_kwargs(task),
    )

    updated = update_task(
        task["id"],
        interaction.user.id,
        "discord_thread_created",
        thread_id=created.thread.id,
        message_id=created.message.id,
    )
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]

    await interaction.followup.send(
        f"Published task from template: {created.thread.mention}",
        ephemeral=True,
    )


async def require_task_assigner(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return False
    if is_task_assigner(interaction.user):
        return True
    await interaction.response.send_message(f"You need the `{settings.task_assigner_role}` role or `{settings.admin_role}` role to use this command.", ephemeral=True)
    return False


async def require_task_manager(interaction: discord.Interaction, task: dict) -> bool:
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return False
    if can_manage_task(interaction.user, task):
        return True
    await interaction.response.send_message("Only admins or the task assigner who created this task can edit it.", ephemeral=True)
    return False


def _attachment_list(*files: Optional[discord.Attachment]) -> list[discord.Attachment]:
    return [f for f in files if f is not None]


@task_group.command(name="help", description="Show all Kanban bot commands")
async def task_help(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=command_help_embed(), ephemeral=True)


@task_group.command(name="info_page", description="Post or refresh the public task-board instruction page")
async def task_info_page(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None) -> None:
    if not interaction.guild:
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return
    if not isinstance(interaction.user, discord.Member) or not is_admin_member(interaction.user):
        await interaction.response.send_message("Only task admins can publish the info page.", ephemeral=True)
        return
    target_channel = channel
    if target_channel is None and settings.info_page_channel_id:
        fetched = interaction.client.get_channel(settings.info_page_channel_id) or await interaction.client.fetch_channel(settings.info_page_channel_id)
        target_channel = fetched if isinstance(fetched, discord.TextChannel) else None
    if target_channel is None and isinstance(interaction.channel, discord.TextChannel):
        target_channel = interaction.channel
    if not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message("Pick a public text channel, set INFO_PAGE_CHANNEL_ID, or run this command inside a text channel.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    message = await target_channel.send(embed=info_page_embed())
    for role in JOB_ROLES:
        emoji = JOB_ROLE_EMOJIS.get(role)
        if emoji:
            await message.add_reaction(emoji)
    set_config(interaction.guild.id, "info_page_message_id", str(message.id))
    await interaction.followup.send(f"Posted the public info page in {target_channel.mention}.", ephemeral=True)


@task_group.command(name="webhook_publish", description="Mirror a task to configured board channels using webhooks")
async def task_webhook_publish(interaction: discord.Interaction, task_id: int) -> None:
    if not interaction.guild:
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    if not await require_task_manager(interaction, task):
        return
    if not settings.webhook_board_channel_ids:
        await interaction.response.send_message("Set WEBHOOK_BOARD_CHANNEL_IDS in your environment first.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    sent = 0
    for channel_id in settings.webhook_board_channel_ids:
        channel = interaction.client.get_channel(channel_id) or await interaction.client.fetch_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            continue
        hooks = await channel.webhooks()
        hook = next((h for h in hooks if h.name == "Task Board Mirror"), None)
        if hook is None:
            hook = await channel.create_webhook(name="Task Board Mirror")
        await hook.send(embed=task_embed(task), username="Task Board", wait=True)
        sent += 1
    await interaction.followup.send(f"Published task #{task_id} to {sent} webhook board channel(s).", ephemeral=True)


@task_group.command(name="create", description="Open the guided task creation dropdown flow")
async def task_create(
    interaction: discord.Interaction,
    thumbnail: Optional[discord.Attachment] = None,
    custom_game_engine: Optional[str] = None,
) -> None:
    thumbnail_url = thumbnail.url if thumbnail else ""
    if thumbnail and thumbnail.content_type and not thumbnail.content_type.startswith("image/"):
        await interaction.response.send_message("The thumbnail must be an image attachment.", ephemeral=True)
        return

    state = CreateTaskState(thumbnail_url=thumbnail_url, custom_game_engine=custom_game_engine or "")
    await interaction.response.send_message(
        embed=create_setup_embed(state),
        view=TaskCreateSetupView(
            interaction.client,  # type: ignore[arg-type]
            interaction.user.id,
            thumbnail_url=thumbnail_url,
            custom_game_engine=custom_game_engine or "",
        ),
        ephemeral=True,
    )


@task_group.command(name="attach", description="Attach up to five images/documents/files to an existing task")
@app_commands.describe(task_id="The task number", file1="First file", file2="Optional file", file3="Optional file", file4="Optional file", file5="Optional file", notes="Optional context")
async def task_attach(
    interaction: discord.Interaction,
    task_id: int,
    file1: discord.Attachment,
    file2: Optional[discord.Attachment] = None,
    file3: Optional[discord.Attachment] = None,
    file4: Optional[discord.Attachment] = None,
    file5: Optional[discord.Attachment] = None,
    notes: Optional[str] = None,
) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    files = _attachment_list(file1, file2, file3, file4, file5)
    await interaction.response.defer(ephemeral=True)
    thread = await fetch_task_thread(interaction.client, task.get("thread_id"))  # type: ignore[arg-type]
    for file in files:
        add_attachment(task_id=task_id, uploader_id=interaction.user.id, filename=file.filename, url=file.url, content_type=file.content_type or "", notes=notes or "")
        if thread:
            await thread.send(f"{interaction.user.mention} attached **{file.filename}** to task #{task_id}." + (f"\nNotes: {notes}" if notes else "") + f"\n{file.url}")
    updated = update_task(task_id, interaction.user.id, "attachments_added")
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
    await interaction.followup.send(f"Attached {len(files)} file(s) to task #{task_id}.", ephemeral=True)


@task_group.command(name="claim", description="Claim a task by ID")
async def task_claim(interaction: discord.Interaction, task_id: int) -> None:
    if not interaction.guild:
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    active_count = count_active_assignments(interaction.user.id, interaction.guild.id)
    if active_count >= settings.max_active_assignments:
        await interaction.response.send_message(f"You already have {active_count} active assignments. The limit is {settings.max_active_assignments}.", ephemeral=True)
        return
    if not get_profile(interaction.guild.id, interaction.user.id):
        await interaction.response.send_modal(ProfileEditModal(guild_id=interaction.guild.id, user_id=interaction.user.id))
        return
    await interaction.response.defer(ephemeral=True)
    ok, message, updated = claim_task(task_id, interaction.user.id)
    if not ok:
        await interaction.followup.send(message, ephemeral=True)
        return
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await notify_claim(interaction.client, updated, interaction.user)  # type: ignore[arg-type]
        await interaction.followup.send(f"You claimed task #{task_id}. Your task profile card was sent to the assigner.", ephemeral=True)


@task_group.command(name="assign", description="Assign a task to a user")
async def task_assign(interaction: discord.Interaction, task_id: int, user: discord.Member) -> None:
    if not interaction.guild:
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    if not await require_task_manager(interaction, task):
        return
    if not get_profile(interaction.guild.id, user.id):
        await interaction.response.send_message(f"{user.mention} has not completed a task profile yet.", ephemeral=True)
        return
    active_count = count_active_assignments(user.id, interaction.guild.id)
    if active_count >= settings.max_active_assignments:
        await interaction.response.send_message(f"{user.mention} already has {active_count} active assignments. The limit is {settings.max_active_assignments}.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    ok, message, updated = claim_task(task_id, user.id)
    if not ok:
        await interaction.followup.send(message, ephemeral=True)
        return
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await notify_claim(interaction.client, updated, user)  # type: ignore[arg-type]
        await interaction.followup.send(f"Assigned/claimed task #{task_id} for {user.mention}. Their task profile card was sent to the assigner.", ephemeral=True)


@task_group.command(name="move", description="Move a task to another status")
@app_commands.choices(status=[app_commands.Choice(name=s, value=s) for s in ["To Do", "In Progress", "Review", "Done"]])
async def task_move(interaction: discord.Interaction, task_id: int, status: app_commands.Choice[str]) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    if not await require_task_manager(interaction, task):
        return
    await interaction.response.defer(ephemeral=True)
    updated = update_task(task_id, interaction.user.id, "status_changed", status=status.value, archived=0)
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(f"Moved task #{task_id} to **{status.value}**.", ephemeral=True)


@task_group.command(name="done", description="Mark a task as Done")
async def task_done(interaction: discord.Interaction, task_id: int) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    if not await require_task_manager(interaction, task):
        return
    await interaction.response.defer(ephemeral=True)
    updated = update_task(task_id, interaction.user.id, "done", status="Done", archived=0)
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(f"Task #{task_id} marked Done.", ephemeral=True)


@task_group.command(name="archive", description="Archive a task but keep it stored")
async def task_archive(interaction: discord.Interaction, task_id: int) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    if not await require_task_manager(interaction, task):
        return
    await interaction.response.defer(ephemeral=True)
    updated = update_task(task_id, interaction.user.id, "archived", status="Archived", archived=1)
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(f"Archived task #{task_id}. It is still stored.", ephemeral=True)


@task_group.command(name="restore", description="Restore an archived task")
async def task_restore(interaction: discord.Interaction, task_id: int) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    if not await require_task_manager(interaction, task):
        return
    await interaction.response.defer(ephemeral=True)
    updated = update_task(task_id, interaction.user.id, "restored", status="To Do", archived=0)
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(f"Restored task #{task_id} to **To Do**.", ephemeral=True)


@task_group.command(name="search", description="Search tasks by major dividers")
@app_commands.choices(
    status=[app_commands.Choice(name=s, value=s) for s in STATUS_CHOICES],
    priority=[app_commands.Choice(name=p, value=p) for p in PRIORITY_CHOICES],
)

# taskbot search v10 choices

@app_commands.choices(
    status=[app_commands.Choice(name=s, value=s) for s in STATUS_CHOICES],
    priority=[app_commands.Choice(name=p, value=p) for p in PRIORITY_CHOICES],
    job_roles=_taskbot_choices(_TASKBOT_JOB_ROLES),
    game_engines=_taskbot_choices(_TASKBOT_GAME_ENGINES),
    dev_environments=_taskbot_choices(_TASKBOT_OS_OPTIONS),
    tag=_taskbot_choices(_TASKBOT_TAG_OPTIONS),
)
@app_commands.describe(
    job_roles="Filter by job role.",
    game_engines="Filter by engine/program.",
    dev_environments="Filter by OS.",
    tag="Filter by tag.",
)

async def task_search(
    interaction: discord.Interaction,
    status: Optional[app_commands.Choice[str]] = None,
    priority: Optional[app_commands.Choice[str]] = None,
    job_roles: Optional[str] = None,
    dev_environments: Optional[str] = None,
    game_engines: Optional[str] = None,
    tag: Optional[str] = None,
    creator: Optional[discord.Member] = None,
    include_archived: bool = False,
) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Search can only be used inside a server.", ephemeral=True)
        return
    results = search_tasks(
        guild_id=interaction.guild.id,
        status=status.value if status else None,
        priority=priority.value if priority else None,
        tag=tag,
        creator_id=creator.id if creator else None,
        job_role=job_roles,
        dev_environment=dev_environments,
        game_engine=game_engines,
        include_archived=include_archived,
        limit=10,
    )
    if not results:
        await interaction.response.send_message("No matching tasks found. For multi-answer fields, separate values with commas, for example `Programmer, UI Artist`.", ephemeral=True)
        return
    lines = []
    for task in results:
        thread = f"<#{task['thread_id']}>" if task.get("thread_id") else "No thread"
        archived = " — archived" if task.get("archived") else ""
        lines.append(f"**#{task['id']}** {thread} — **{task['status']}** — {task.get('task_type') or 'Feature'} — {task.get('job_role')} — {task.get('dev_environment')} — {task.get('game_engine')}{archived}\n{task['title']}")
    await interaction.response.send_message("\n\n".join(lines), ephemeral=True)


@task_group.command(name="dashboard", description="Show your personal board and task-assigner dashboard")
async def task_dashboard(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return

    personal_tasks = search_tasks(
        guild_id=interaction.guild.id,
        claimer_id=interaction.user.id,
        include_archived=True,
        limit=50,
    )
    assigner_allowed = isinstance(interaction.user, discord.Member) and is_task_assigner(interaction.user)
    assigner_tasks = search_tasks(
        guild_id=interaction.guild.id,
        creator_id=interaction.user.id,
        include_archived=True,
        limit=50,
    ) if assigner_allowed else []

    await interaction.response.send_message(
        embed=dashboard_board_embed(
            interaction.user,
            personal_tasks,
            assigner_tasks,
            is_assigner_user=assigner_allowed,
            mode="personal_horizontal",
            show_closed=False,
        ),
        view=DashboardView(interaction.client, interaction.guild.id, interaction.user.id, assigner_allowed),  # type: ignore[arg-type]
        ephemeral=True,
    )


@task_group.command(name="profile", description="Show a bot-generated task profile card")
async def task_profile(interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
    if not interaction.guild:
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return
    target = user or interaction.user
    stats = get_profile_stats(target.id, interaction.guild.id)
    profile = get_profile(interaction.guild.id, target.id)
    await interaction.response.send_message(embed=profile_embed(target, stats, settings.max_active_assignments, profile), view=ProfileCardView(target.id, interaction.guild.id), ephemeral=True)



@task_group.command(name="edit_profile", description="Edit your task profile card")
async def task_edit_profile(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return
    existing = get_profile(interaction.guild.id, interaction.user.id)
    await interaction.response.send_modal(ProfileEditModal(guild_id=interaction.guild.id, user_id=interaction.user.id, existing=existing))


@task_group.command(name="send_profile", description="Send your task profile card to a task assigner for a specific task")
async def task_send_profile(interaction: discord.Interaction, task_id: int) -> None:
    if not interaction.guild:
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    creator = await interaction.client.fetch_user(task["creator_id"])
    stats = get_profile_stats(interaction.user.id, interaction.guild.id)
    profile = get_profile(interaction.guild.id, interaction.user.id)
    embed = profile_embed(interaction.user, stats, settings.max_active_assignments, profile)
    view = ProfileCardView(interaction.user.id, interaction.guild.id)
    try:
        await creator.send(f"{interaction.user.mention} sent their task profile for **#{task['id']} — {task['title']}**.", embed=embed, view=view)
        ok = True
    except discord.HTTPException:
        ok = False
    thread = await fetch_task_thread(interaction.client, task.get("claim_thread_id") or task.get("thread_id"))  # type: ignore[arg-type]
    if thread:
        await thread.send(f"Task profile from {interaction.user.mention}:", embed=embed, view=ProfileCardView(interaction.user.id, interaction.guild.id))
        ok = True
    await interaction.followup.send("Profile card sent." if ok else "Could not send the profile card; the assigner may have DMs disabled and there is no task thread available.", ephemeral=True)


@task_group.command(name="edit", description="Edit an existing task you created")
async def task_edit(interaction: discord.Interaction, task_id: int, thumbnail: Optional[discord.Attachment] = None) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    if thumbnail and thumbnail.content_type and not thumbnail.content_type.startswith("image/"):
        await interaction.response.send_message("The replacement thumbnail must be an image attachment.", ephemeral=True)
        return
    if not await require_task_manager(interaction, task):
        return
    await interaction.response.send_modal(TaskEditModal(interaction.client, task, thumbnail_url=thumbnail.url if thumbnail else ""))  # type: ignore[arg-type]


@task_edit.autocomplete("task_id")
async def task_edit_task_id_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return []
    creator_id = None if is_admin_member(interaction.user) else interaction.user.id
    tasks = search_tasks(guild_id=interaction.guild.id, creator_id=creator_id, include_archived=True, limit=25)
    choices: list[app_commands.Choice[int]] = []
    needle = current.strip().lower()
    for task in tasks:
        haystack = f"{task['id']} {task.get('title', '')} {task.get('status', '')}".lower()
        if needle and needle not in haystack:
            continue
        bucket = "ARCHIVED" if task.get("archived") else "ACTIVE"
        name = f"{bucket} #{task['id']} — {task.get('title', 'Untitled')}"[:100]
        choices.append(app_commands.Choice(name=name, value=int(task["id"])))
        if len(choices) >= 25:
            break
    return choices


@task_group.command(name="info", description="Show one task by ID")
async def task_info(interaction: discord.Interaction, task_id: int) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    await interaction.response.send_message(embed=task_embed(task), ephemeral=True)


@task_group.command(name="set_due", description="Set or update a task due date")
async def task_set_due(interaction: discord.Interaction, task_id: int, due_date: str) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return
    if not await require_task_manager(interaction, task):
        return
    try:
        parsed = parse_due_date_to_iso(due_date)
    except ValueError:
        await interaction.response.send_message("Could not parse due date. Use `YYYY-MM-DD`.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    updated = update_task(task_id, interaction.user.id, "due_date_changed", due_date=parsed)
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(f"Updated task #{task_id} due date to `{parsed}`.", ephemeral=True)


@template_group.command(name="save", description="Save a reusable task template")
@app_commands.choices(
    positions_needed=[app_commands.Choice(name=str(n), value=n) for n in POSITIONS_NEEDED_CHOICES],
    game_engine=[app_commands.Choice(name=x, value=x) for x in GAME_ENGINES],
)
async def template_save(
    interaction: discord.Interaction,
    name: str,
    positions_needed: app_commands.Choice[int],
    game_engine: app_commands.Choice[str],
    job_roles: str = "Programmer",
    dev_environments: str = "Windows",
    custom_game_engine: Optional[str] = None,
    game_programs: Optional[str] = None,
    task_types: str = "Feature",
    thumbnail: Optional[discord.Attachment] = None,
) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Templates only work inside a server.", ephemeral=True)
        return
    if not await require_task_assigner(interaction):
        return
    await interaction.response.send_modal(TemplateSaveModal(
        guild_id=interaction.guild.id,
        owner_id=interaction.user.id,
        name=name,
        thumbnail_url=thumbnail.url if thumbnail else "",
        positions_needed=positions_needed.value,
        job_role=job_roles,
        dev_environment=normalize_dev_environments(dev_environments),
        game_engine=game_engine.value,
        custom_game_engine=custom_game_engine or "",
        game_programs=game_programs or "",
    ))


@template_group.command(name="edit", description="Edit a template with the same guided dropdown flow as task create")
async def template_edit(
    interaction: discord.Interaction,
    name: str,
    thumbnail: Optional[discord.Attachment] = None,
    custom_game_engine: Optional[str] = None,
) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Templates only work inside a server.", ephemeral=True)
        return
    if not await require_task_assigner(interaction):
        return

    template = get_template(interaction.guild.id, interaction.user.id, name)
    if not template:
        await interaction.response.send_message("Template not found. Use `/template save` first.", ephemeral=True)
        return

    if thumbnail and thumbnail.content_type and not thumbnail.content_type.startswith("image/"):
        await interaction.response.send_message("The template thumbnail must be an image attachment.", ephemeral=True)
        return

    if thumbnail or custom_game_engine:
        template = dict(template)
        if thumbnail:
            template["thumbnail_url"] = thumbnail.url
        if custom_game_engine:
            template["custom_game_engine"] = custom_game_engine

    await interaction.response.send_message(
        "Edit dropdown/category values first, then continue to the template form to save changes.",
        embed=template_edit_setup_embed(template, page=1),
        view=TemplateEditStepOneView(template, interaction.user.id),
        ephemeral=True,
    )



@template_group.command(name="use", description="Import a saved template into the create form")
async def template_use(
    interaction: discord.Interaction,
    name: str,
    thumbnail: Optional[discord.Attachment] = None,
    custom_game_engine: Optional[str] = None,
    publish_now: bool = False,
) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Templates only work inside a server.", ephemeral=True)
        return

    template = get_template(interaction.guild.id, interaction.user.id, name)
    if not template:
        await interaction.response.send_message("Template not found.", ephemeral=True)
        return

    if publish_now:
        await interaction.response.defer(ephemeral=True)
        await publish_template_as_task_now(interaction, template)
        return

    await interaction.response.send_modal(
        TaskCreateModal(
            interaction.client,  # type: ignore[arg-type]
            thumbnail_url=thumbnail.url if thumbnail else template.get("thumbnail_url", ""),
            positions_needed=int(template.get("positions_needed") or 1),
            job_role=template.get("job_role", "Programmer"),
            dev_environment=template.get("dev_environment") or template.get("dev_environments") or "Windows",
            game_engine=template.get("game_engine", "Unity"),
            custom_game_engine=custom_game_engine or template.get("custom_game_engine", ""),
            task_types=template.get("task_types", "") or template.get("tags", ""),
            template=template,
        )
    )


@template_group.command(name="view", description="Display one saved template as an editable Discord module")
async def template_view(interaction: discord.Interaction, name: str) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Templates only work inside a server.", ephemeral=True)
        return
    template = get_template(interaction.guild.id, interaction.user.id, name)
    if not template:
        await interaction.response.send_message("Template not found.", ephemeral=True)
        return
    await interaction.response.send_message(embed=template_embed(template), view=TemplateDetailView(interaction.client, template), ephemeral=True)  # type: ignore[arg-type]


@template_group.command(name="list", description="List your saved templates")
async def template_list(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Templates only work inside a server.", ephemeral=True)
        return

    templates = list_templates(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(
        embed=template_list_embed(templates),
        view=TemplateListView(templates, interaction.user.id),
        ephemeral=True,
    )


@template_group.command(name="delete", description="Delete one of your templates")
async def template_delete(interaction: discord.Interaction, name: str) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Templates only work inside a server.", ephemeral=True)
        return
    deleted = delete_template(interaction.guild.id, interaction.user.id, name)
    await interaction.response.send_message(f"Deleted template `{name}`." if deleted else "Template not found.", ephemeral=True)
