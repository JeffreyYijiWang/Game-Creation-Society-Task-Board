from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from taskbot.config import settings
from taskbot.constants import DEV_ENVIRONMENTS, GAME_ENGINES, JOB_ROLES, POSITIONS_NEEDED_CHOICES, PRIORITY_CHOICES, STATUS_CHOICES
from taskbot.db import (
    add_attachment,
    claim_task,
    count_active_assignments,
    delete_template,
    get_profile,
    get_profile_stats,
    get_task,
    get_template,
    list_templates,
    search_tasks,
    update_task,
)
from taskbot.embeds import command_help_embed, dashboard_embed, profile_embed, task_embed, template_embed
from taskbot.forum import fetch_task_thread, sync_discord_task
from taskbot.modals import ProfileEditModal, TaskCreateModal, TemplateSaveModal
from taskbot.notifications import notify_claim
from taskbot.utils import normalize_dev_environments, parse_due_date_to_iso
from taskbot.views import ProfileCardView, TaskCreateWizardView, TemplateDetailView


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
    return any(role.name == settings.task_assigner_role for role in member.roles)


async def require_task_assigner(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return False
    if member_has_task_assigner_role(interaction.user) or interaction.user.guild_permissions.manage_guild:
        return True
    await interaction.response.send_message(f"You need the `{settings.task_assigner_role}` role to use this command.", ephemeral=True)
    return False


def _attachment_list(*files: Optional[discord.Attachment]) -> list[discord.Attachment]:
    return [f for f in files if f is not None]


@task_group.command(name="help", description="Show all Kanban bot commands")
async def task_help(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=command_help_embed(), ephemeral=True)


@task_group.command(name="create", description="Open the guided task creator with dropdowns and optional thumbnail")
async def task_create(interaction: discord.Interaction, thumbnail: Optional[discord.Attachment] = None, custom_game_engine: Optional[str] = None) -> None:
    if thumbnail and thumbnail.content_type and not thumbnail.content_type.startswith("image/"):
        await interaction.response.send_message("The thumbnail must be an image attachment.", ephemeral=True)
        return
    await interaction.response.send_message(
        "Choose the major dividers below, including one or more development environments. Then press **Continue to form**.",
        ephemeral=True,
        view=TaskCreateWizardView(interaction.client, interaction.user.id, thumbnail.url if thumbnail else "", custom_game_engine or ""),  # type: ignore[arg-type]
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
    await interaction.response.defer(ephemeral=True)
    updated = update_task(task_id, interaction.user.id, "restored", status="To Do", archived=0)
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(f"Restored task #{task_id} to **To Do**.", ephemeral=True)


@task_group.command(name="search", description="Search tasks by major dividers")
@app_commands.choices(
    status=[app_commands.Choice(name=s, value=s) for s in STATUS_CHOICES],
    priority=[app_commands.Choice(name=p, value=p) for p in PRIORITY_CHOICES],
    job_role=[app_commands.Choice(name=x, value=x) for x in JOB_ROLES],
    dev_environment=[app_commands.Choice(name=x, value=x) for x in DEV_ENVIRONMENTS],
    game_engine=[app_commands.Choice(name=x, value=x) for x in GAME_ENGINES],
)
async def task_search(
    interaction: discord.Interaction,
    status: Optional[app_commands.Choice[str]] = None,
    priority: Optional[app_commands.Choice[str]] = None,
    tag: Optional[str] = None,
    claimer: Optional[discord.Member] = None,
    creator: Optional[discord.Member] = None,
    job_role: Optional[app_commands.Choice[str]] = None,
    dev_environment: Optional[app_commands.Choice[str]] = None,
    game_engine: Optional[app_commands.Choice[str]] = None,
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
        claimer_id=claimer.id if claimer else None,
        creator_id=creator.id if creator else None,
        job_role=job_role.value if job_role else None,
        dev_environment=dev_environment.value if dev_environment else None,
        game_engine=game_engine.value if game_engine else None,
        include_archived=include_archived,
        limit=10,
    )
    if not results:
        await interaction.response.send_message("No matching tasks found.", ephemeral=True)
        return
    lines = []
    for task in results:
        thread = f"<#{task['thread_id']}>" if task.get("thread_id") else "No thread"
        archived = " — archived" if task.get("archived") else ""
        lines.append(f"**#{task['id']}** {thread} — **{task['status']}** — {task.get('job_role')} — {task.get('dev_environment')} — {task.get('game_engine')}{archived}\n{task['title']}")
    await interaction.response.send_message("\n\n".join(lines), ephemeral=True)


@task_group.command(name="dashboard", description="Task-assigner dashboard for tasks you created")
async def task_dashboard(interaction: discord.Interaction, include_archived: bool = True) -> None:
    if not interaction.guild:
        await interaction.response.send_message("This command only works inside a server.", ephemeral=True)
        return
    if not await require_task_assigner(interaction):
        return
    tasks = search_tasks(guild_id=interaction.guild.id, creator_id=interaction.user.id, include_archived=include_archived, limit=20)
    await interaction.response.send_message(embed=dashboard_embed(interaction.user, tasks, include_archived), ephemeral=True)


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
    job_role=[app_commands.Choice(name=x, value=x) for x in JOB_ROLES],
    game_engine=[app_commands.Choice(name=x, value=x) for x in GAME_ENGINES],
)
async def template_save(
    interaction: discord.Interaction,
    name: str,
    positions_needed: app_commands.Choice[int],
    job_role: app_commands.Choice[str],
    game_engine: app_commands.Choice[str],
    dev_environments: str = "Windows",
    custom_game_engine: Optional[str] = None,
    thumbnail: Optional[discord.Attachment] = None,
) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Templates only work inside a server.", ephemeral=True)
        return
    await interaction.response.send_modal(TemplateSaveModal(
        guild_id=interaction.guild.id,
        owner_id=interaction.user.id,
        name=name,
        thumbnail_url=thumbnail.url if thumbnail else "",
        positions_needed=positions_needed.value,
        job_role=job_role.value,
        dev_environment=normalize_dev_environments(dev_environments),
        game_engine=game_engine.value,
        custom_game_engine=custom_game_engine or "",
    ))


@template_group.command(name="edit", description="Edit an existing template")
@app_commands.choices(
    positions_needed=[app_commands.Choice(name=str(n), value=n) for n in POSITIONS_NEEDED_CHOICES],
    job_role=[app_commands.Choice(name=x, value=x) for x in JOB_ROLES],
    game_engine=[app_commands.Choice(name=x, value=x) for x in GAME_ENGINES],
)
async def template_edit(
    interaction: discord.Interaction,
    name: str,
    positions_needed: app_commands.Choice[int],
    job_role: app_commands.Choice[str],
    game_engine: app_commands.Choice[str],
    dev_environments: str = "Windows",
    custom_game_engine: Optional[str] = None,
    thumbnail: Optional[discord.Attachment] = None,
) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Templates only work inside a server.", ephemeral=True)
        return
    existing = get_template(interaction.guild.id, interaction.user.id, name)
    if not existing:
        await interaction.response.send_message("Template not found. Use `/template save` first.", ephemeral=True)
        return
    await interaction.response.send_modal(TemplateSaveModal(
        guild_id=interaction.guild.id,
        owner_id=interaction.user.id,
        name=name,
        thumbnail_url=thumbnail.url if thumbnail else existing.get("thumbnail_url", ""),
        positions_needed=positions_needed.value,
        job_role=job_role.value,
        dev_environment=normalize_dev_environments(dev_environments),
        game_engine=game_engine.value,
        custom_game_engine=custom_game_engine or existing.get("custom_game_engine", ""),
        existing=existing,
    ))


@template_group.command(name="use", description="Import a saved template into the create wizard")
async def template_use(interaction: discord.Interaction, name: str, thumbnail: Optional[discord.Attachment] = None, custom_game_engine: Optional[str] = None) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Templates only work inside a server.", ephemeral=True)
        return
    template = get_template(interaction.guild.id, interaction.user.id, name)
    if not template:
        await interaction.response.send_message("Template not found.", ephemeral=True)
        return
    if thumbnail:
        template = dict(template)
        template["thumbnail_url"] = thumbnail.url
    await interaction.response.send_message("Template loaded. Adjust dropdowns if needed, then press **Continue to form**.", ephemeral=True, view=TaskCreateWizardView(interaction.client, interaction.user.id, custom_game_engine=custom_game_engine or template.get("custom_game_engine", ""), template=template))  # type: ignore[arg-type]


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
    if not templates:
        await interaction.response.send_message("You have no templates yet.", ephemeral=True)
        return
    lines = [f"`{t['name']}` — {t.get('job_role')} — {t.get('game_engine')} — {t.get('positions_needed')} needed — {t.get('dev_environment')}\n{t.get('title') or 'Untitled'}" for t in templates[:20]]
    await interaction.response.send_message("\n\n".join(lines), ephemeral=True)


@template_group.command(name="delete", description="Delete one of your templates")
async def template_delete(interaction: discord.Interaction, name: str) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Templates only work inside a server.", ephemeral=True)
        return
    deleted = delete_template(interaction.guild.id, interaction.user.id, name)
    await interaction.response.send_message(f"Deleted template `{name}`." if deleted else "Template not found.", ephemeral=True)
