from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from taskbot.config import settings
from taskbot.constants import DEV_ENVIRONMENTS, GAME_ENGINES, JOB_ROLES, POSITIONS_NEEDED_CHOICES
from taskbot.db import (
    claim_task,
    count_active_assignments,
    delete_template,
    get_profile,
    get_profile_stats,
    get_task_by_message,
    get_task_by_thread,
    list_user_projects,
    update_task,
)
from taskbot.forum import sync_discord_task
from taskbot.embeds import profile_embed


class TaskControls(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def get_task_from_interaction(self, interaction: discord.Interaction) -> Optional[dict]:
        if isinstance(interaction.channel, discord.Thread):
            return get_task_by_thread(interaction.channel.id)
        if interaction.message:
            return get_task_by_message(interaction.message.id)
        return None

    async def change_status(self, interaction: discord.Interaction, status: str, archived: int = 0) -> None:
        task = await self.get_task_from_interaction(interaction)
        if not task:
            await interaction.response.send_message("Could not find this task in the database.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        updated = update_task(task["id"], interaction.user.id, "status_changed", status=status, archived=archived)
        if updated:
            await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
            await interaction.followup.send(f"Task #{updated['id']} moved to **{status}**.", ephemeral=True)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, custom_id="taskbot:claim", row=0)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        task = await self.get_task_from_interaction(interaction)
        if not task:
            await interaction.response.send_message("Could not find this task in the database.", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("Tasks can only be claimed inside a server.", ephemeral=True)
            return
        active_count = count_active_assignments(interaction.user.id, interaction.guild.id)
        if active_count >= settings.max_active_assignments:
            await interaction.response.send_message(f"You already have {active_count} active assignments. The limit is {settings.max_active_assignments}.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok, message, updated = claim_task(task["id"], interaction.user.id)
        if not ok:
            await interaction.followup.send(message, ephemeral=True)
            return
        if updated:
            await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
            from taskbot.notifications import notify_claim
            await notify_claim(interaction.client, updated, interaction.user)  # type: ignore[arg-type]
            await interaction.followup.send(f"You claimed task #{updated['id']}. Your task profile card was sent to the assigner.", ephemeral=True)

    @discord.ui.button(label="In Progress", style=discord.ButtonStyle.secondary, custom_id="taskbot:in_progress", row=0)
    async def in_progress(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.change_status(interaction, "In Progress")

    @discord.ui.button(label="Review", style=discord.ButtonStyle.secondary, custom_id="taskbot:review", row=0)
    async def review(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.change_status(interaction, "Review")

    @discord.ui.button(label="Done", style=discord.ButtonStyle.success, custom_id="taskbot:done", row=0)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.change_status(interaction, "Done")

    @discord.ui.button(label="Comment", style=discord.ButtonStyle.secondary, custom_id="taskbot:comment", row=1)
    async def comment(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from taskbot.modals import CommentModal
        await interaction.response.send_modal(CommentModal())

    @discord.ui.button(label="Archive", style=discord.ButtonStyle.danger, custom_id="taskbot:archive", row=1)
    async def archive(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.change_status(interaction, "Archived", archived=1)


class TaskCreateWizardView(discord.ui.View):
    def __init__(self, bot: commands.Bot, owner_id: int, thumbnail_url: str = "", custom_game_engine: str = "", template: dict | None = None) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.owner_id = owner_id
        self.thumbnail_url = thumbnail_url or (template or {}).get("thumbnail_url", "")
        self.custom_game_engine = custom_game_engine or (template or {}).get("custom_game_engine", "")
        self.job_role = (template or {}).get("job_role", "Programmer")
        self.positions_needed = int((template or {}).get("positions_needed", 1))
        self.dev_environment = (template or {}).get("dev_environment", "Windows")
        self.game_engine = (template or {}).get("game_engine", "Unity")
        self.template = template
        self.add_item(JobRoleSelect(self))
        self.add_item(PositionsSelect(self))
        self.add_item(DevEnvironmentMultiSelect(self))
        self.add_item(GameEngineSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this wizard can use it.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Continue to form", style=discord.ButtonStyle.success, row=4)
    async def continue_form(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from taskbot.modals import TaskCreateModal
        await interaction.response.send_modal(TaskCreateModal(
            self.bot,
            thumbnail_url=self.thumbnail_url,
            positions_needed=self.positions_needed,
            job_role=self.job_role,
            dev_environment=self.dev_environment,
            game_engine=self.game_engine,
            custom_game_engine=self.custom_game_engine,
            template=self.template,
        ))


class JobRoleSelect(discord.ui.Select):
    def __init__(self, parent: TaskCreateWizardView) -> None:
        self.parent_view = parent
        options = [discord.SelectOption(label=x, value=x, default=(x == parent.job_role)) for x in JOB_ROLES]
        super().__init__(placeholder="Job description / role", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.job_role = self.values[0]
        await interaction.response.defer(ephemeral=True)


class PositionsSelect(discord.ui.Select):
    def __init__(self, parent: TaskCreateWizardView) -> None:
        self.parent_view = parent
        options = [discord.SelectOption(label=str(n), value=str(n), default=(n == parent.positions_needed)) for n in POSITIONS_NEEDED_CHOICES]
        super().__init__(placeholder="Number of people needed", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.positions_needed = int(self.values[0])
        await interaction.response.defer(ephemeral=True)


class DevEnvironmentMultiSelect(discord.ui.Select):
    def __init__(self, parent: TaskCreateWizardView) -> None:
        self.parent_view = parent
        current = {x.strip() for x in str(parent.dev_environment).split(",") if x.strip()}
        options = [discord.SelectOption(label=x, value=x, default=(x in current)) for x in DEV_ENVIRONMENTS]
        super().__init__(placeholder="Development environments; choose one or more", min_values=1, max_values=len(DEV_ENVIRONMENTS), options=options, row=2)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.dev_environment = ", ".join(self.values)
        await interaction.response.defer(ephemeral=True)


class GameEngineSelect(discord.ui.Select):
    def __init__(self, parent: TaskCreateWizardView) -> None:
        self.parent_view = parent
        options = [discord.SelectOption(label=x, value=x, default=(x == parent.game_engine)) for x in GAME_ENGINES]
        super().__init__(placeholder="Game engine", min_values=1, max_values=1, options=options, row=3)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.game_engine = self.values[0]
        await interaction.response.defer(ephemeral=True)


class ProfileCardView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int) -> None:
        super().__init__(timeout=900)
        self.user_id = user_id
        self.guild_id = guild_id

    @discord.ui.button(label="View worked projects", style=discord.ButtonStyle.primary)
    async def view_projects(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        projects = list_user_projects(self.user_id, self.guild_id, limit=12)
        if not projects:
            await interaction.response.send_message("No claimed/completed projects are recorded for this profile yet.", ephemeral=True)
            return
        lines = []
        for task in projects:
            thread = f"<#{task['thread_id']}>" if task.get("thread_id") else "No thread"
            lines.append(f"**#{task['id']}** {thread} — **{task['status']}** — {task.get('job_role')}\n{task['title']}")
        await interaction.response.send_message("\n\n".join(lines)[:1900], ephemeral=True)


class TemplateDetailView(discord.ui.View):
    def __init__(self, bot: commands.Bot, template: dict) -> None:
        super().__init__(timeout=900)
        self.bot = bot
        self.template = template

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != int(self.template["owner_id"]):
            await interaction.response.send_message("Only the template owner can use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.success)
    async def use_template(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Choose any dropdown changes, then press **Continue to form**.", ephemeral=True, view=TaskCreateWizardView(self.bot, interaction.user.id, template=self.template))

    @discord.ui.button(label="Edit Template", style=discord.ButtonStyle.primary)
    async def edit_template(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from taskbot.modals import TemplateSaveModal
        await interaction.response.send_modal(TemplateSaveModal(
            guild_id=int(self.template["guild_id"]),
            owner_id=int(self.template["owner_id"]),
            name=self.template["name"],
            thumbnail_url=self.template.get("thumbnail_url", ""),
            positions_needed=int(self.template.get("positions_needed") or 1),
            job_role=self.template.get("job_role", "Programmer"),
            dev_environment=self.template.get("dev_environment", "Windows"),
            game_engine=self.template.get("game_engine", "Unity"),
            custom_game_engine=self.template.get("custom_game_engine", ""),
            existing=self.template,
        ))

    @discord.ui.button(label="Delete Template", style=discord.ButtonStyle.danger)
    async def delete_template_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ok = delete_template(int(self.template["guild_id"]), int(self.template["owner_id"]), self.template["name"])
        await interaction.response.send_message(f"Deleted `{self.template['name']}`." if ok else "Template was already deleted.", ephemeral=True)
