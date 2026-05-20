from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from taskbot.config import settings
from taskbot.constants import DEV_ENVIRONMENTS, GAME_ENGINES, JOB_ROLES, POSITIONS_NEEDED_CHOICES, TASK_TYPES
from taskbot.access import can_manage_task
from taskbot.db import (
    claim_task,
    count_active_assignments,
    delete_template,
    get_profile,
    get_task_by_message,
    get_task_by_thread,
    list_templates,
    list_user_projects,
    search_tasks,
    update_task,
)
from taskbot.forum import sync_discord_task
from taskbot.embeds import create_guidance_embed, dashboard_board_embed, profile_embed, template_embed


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
        if not isinstance(interaction.user, discord.Member) or not can_manage_task(interaction.user, task):
            await interaction.response.send_message("Only admins or the task assigner who created this task can edit its status/archive state.", ephemeral=True)
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
        if not get_profile(interaction.guild.id, interaction.user.id):
            from taskbot.modals import ProfileEditModal
            await interaction.response.send_modal(ProfileEditModal(guild_id=interaction.guild.id, user_id=interaction.user.id))
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
    def __init__(
        self,
        bot: commands.Bot,
        owner_id: int,
        thumbnail_url: str = "",
        custom_game_engine: str = "",
        template: dict | None = None,
        mode: str = "task_create",
        stage: str = "main",
    ) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.owner_id = owner_id
        self.thumbnail_url = thumbnail_url or (template or {}).get("thumbnail_url", "")
        self.custom_game_engine = custom_game_engine or (template or {}).get("custom_game_engine", "")
        self.job_role = (template or {}).get("job_role", "Programmer")
        self.positions_needed = int((template or {}).get("positions_needed", 1))
        self.dev_environment = (template or {}).get("dev_environment", "Windows")
        self.game_engine = (template or {}).get("game_engine", "Unity")
        self.game_programs = (template or {}).get("game_programs", "")
        self.task_type = (template or {}).get("task_type", "Feature")
        self.template = template
        self.mode = mode
        self.stage = stage

        continue_label = "Continue to form" if stage == "engine" else "Next: engine/tools"
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label == "Continue to form":
                child.label = continue_label

        if stage == "engine":
            self.add_item(GameEngineSelect(self))
        else:
            self.add_item(JobRoleSelect(self))
            self.add_item(PositionsSelect(self))
            self.add_item(DevEnvironmentMultiSelect(self))
            self.add_item(TaskTypeMultiSelect(self))

    def state_template(self) -> dict:
        data = dict(self.template or {})
        data.update(
            {
                "thumbnail_url": self.thumbnail_url,
                "custom_game_engine": self.custom_game_engine,
                "job_role": self.job_role,
                "positions_needed": self.positions_needed,
                "dev_environment": self.dev_environment,
                "game_engine": self.game_engine,
                "game_programs": self.game_programs,
                "task_type": self.task_type,
            }
        )
        return data

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this wizard can use it.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=4)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.stage != "engine":
            await interaction.response.send_message("You are already on the first dropdown step.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=create_guidance_embed(stage="main"),
            view=TaskCreateWizardView(self.bot, self.owner_id, template=self.state_template(), mode=self.mode, stage="main"),
        )

    @discord.ui.button(label="Continue to form", style=discord.ButtonStyle.success, row=4)
    async def continue_form(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from taskbot.modals import TaskCreateModal, TemplateSaveModal
        if self.stage != "engine":
            await interaction.response.edit_message(
                embed=create_guidance_embed(stage="engine"),
                view=TaskCreateWizardView(self.bot, self.owner_id, template=self.state_template(), mode=self.mode, stage="engine"),
            )
            return
        if self.mode == "template_edit" and self.template:
            await interaction.response.send_modal(TemplateSaveModal(
                guild_id=int(self.template["guild_id"]),
                owner_id=int(self.template["owner_id"]),
                name=self.template["name"],
                thumbnail_url=self.thumbnail_url,
                positions_needed=self.positions_needed,
                job_role=self.job_role,
                dev_environment=self.dev_environment,
                game_engine=self.game_engine,
                custom_game_engine=self.custom_game_engine,
                game_programs=self.game_programs,
                task_type=self.task_type,
                existing=self.template,
            ))
            return
        await interaction.response.send_modal(TaskCreateModal(
            self.bot,
            thumbnail_url=self.thumbnail_url,
            positions_needed=self.positions_needed,
            job_role=self.job_role,
            dev_environment=self.dev_environment,
            game_engine=self.game_engine,
            custom_game_engine=self.custom_game_engine,
            game_programs=self.game_programs,
            task_type=self.task_type,
            template=self.template,
        ))


class JobRoleSelect(discord.ui.Select):
    def __init__(self, parent: TaskCreateWizardView) -> None:
        self.parent_view = parent
        current = {x.strip() for x in str(parent.job_role).split(",") if x.strip()}
        options = [discord.SelectOption(label=x, value=x, description="Role needed for this task", default=(x in current)) for x in JOB_ROLES]
        super().__init__(placeholder="1) Job descriptions / roles needed — choose one or more", min_values=1, max_values=min(5, len(JOB_ROLES)), options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.job_role = ", ".join(self.values)
        await interaction.response.defer(ephemeral=True)


class PositionsSelect(discord.ui.Select):
    def __init__(self, parent: TaskCreateWizardView) -> None:
        self.parent_view = parent
        options = [discord.SelectOption(label=str(n), value=str(n), description=f"Stop accepting claims after {n} person/people", default=(n == parent.positions_needed)) for n in POSITIONS_NEEDED_CHOICES]
        super().__init__(placeholder="2) Number of people needed / job capacity", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.positions_needed = int(self.values[0])
        await interaction.response.defer(ephemeral=True)


class DevEnvironmentMultiSelect(discord.ui.Select):
    def __init__(self, parent: TaskCreateWizardView) -> None:
        self.parent_view = parent
        current = {x.strip() for x in str(parent.dev_environment).split(",") if x.strip()}
        options = [discord.SelectOption(label=x, value=x, description="Platform/environment the task supports", default=(x in current)) for x in DEV_ENVIRONMENTS]
        super().__init__(placeholder="3) Development environments — choose all that apply", min_values=1, max_values=len(DEV_ENVIRONMENTS), options=options, row=2)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.dev_environment = ", ".join(self.values)
        await interaction.response.defer(ephemeral=True)


class TaskTypeMultiSelect(discord.ui.Select):
    def __init__(self, parent: TaskCreateWizardView) -> None:
        self.parent_view = parent
        current = {x.strip() for x in str(parent.task_type).split(",") if x.strip()}
        options = [discord.SelectOption(label=x, value=x, description="Major search divider for this task", default=(x in current)) for x in TASK_TYPES]
        super().__init__(placeholder="4) Type of task — Bug Fix, Feature, Art, Research, etc.", min_values=1, max_values=min(5, len(TASK_TYPES)), options=options, row=3)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.task_type = ", ".join(self.values)
        await interaction.response.defer(ephemeral=True)


class GameEngineSelect(discord.ui.Select):
    def __init__(self, parent: TaskCreateWizardView) -> None:
        self.parent_view = parent
        options = [discord.SelectOption(label=x, value=x, description="Main engine or mark Other", default=(x == parent.game_engine)) for x in GAME_ENGINES]
        super().__init__(placeholder="5) Primary game engine", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.game_engine = self.values[0]
        await interaction.response.defer(ephemeral=True)


class DashboardView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        guild_id: int,
        user_id: int,
        assigner_allowed: bool,
        *,
        mode: str = "personal_horizontal",
        show_closed: bool = False,
    ) -> None:
        super().__init__(timeout=900)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.assigner_allowed = assigner_allowed
        self.mode = mode
        self.show_closed = show_closed
        self._refresh_button_labels()

    def _refresh_button_labels(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id == "taskbot:dashboard_toggle_closed":
                child.label = "Hide Done + Archived" if self.show_closed else "Show Done + Archived"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the dashboard owner can use these buttons.", ephemeral=True)
            return False
        return True

    def _tasks(self) -> tuple[list[dict], list[dict]]:
        personal_tasks = search_tasks(
            guild_id=self.guild_id,
            claimer_id=self.user_id,
            include_archived=True,
            limit=50,
        )
        assigner_tasks = search_tasks(
            guild_id=self.guild_id,
            creator_id=self.user_id,
            include_archived=True,
            limit=50,
        ) if self.assigner_allowed else []
        return personal_tasks, assigner_tasks

    async def _render(self, interaction: discord.Interaction, *, mode: str | None = None, show_closed: bool | None = None) -> None:
        next_mode = mode or self.mode
        next_show_closed = self.show_closed if show_closed is None else show_closed
        personal_tasks, assigner_tasks = self._tasks()
        await interaction.response.edit_message(
            embed=dashboard_board_embed(
                interaction.user,
                personal_tasks,
                assigner_tasks,
                is_assigner_user=self.assigner_allowed,
                mode=next_mode,
                show_closed=next_show_closed,
            ),
            view=DashboardView(
                self.bot,
                self.guild_id,
                self.user_id,
                self.assigner_allowed,
                mode=next_mode,
                show_closed=next_show_closed,
            ),
        )

    @discord.ui.button(label="Personal Board", style=discord.ButtonStyle.primary, row=0)
    async def personal_horizontal(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._render(interaction, mode="personal_horizontal")

    @discord.ui.button(label="Personal Vertical", style=discord.ButtonStyle.secondary, row=0)
    async def personal_vertical(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._render(interaction, mode="personal_vertical")

    @discord.ui.button(label="Assigner List", style=discord.ButtonStyle.secondary, row=1)
    async def assigner_list(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.assigner_allowed:
            await interaction.response.send_message("You need task-assigner/admin access to view the assigner dashboard.", ephemeral=True)
            return
        await self._render(interaction, mode="assigner_list")

    @discord.ui.button(label="Assigner Kanban", style=discord.ButtonStyle.secondary, row=1)
    async def assigner_horizontal(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.assigner_allowed:
            await interaction.response.send_message("You need task-assigner/admin access to view the assigner dashboard.", ephemeral=True)
            return
        await self._render(interaction, mode="assigner_horizontal")

    @discord.ui.button(label="Assigner Vertical", style=discord.ButtonStyle.secondary, row=1)
    async def assigner_vertical(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.assigner_allowed:
            await interaction.response.send_message("You need task-assigner/admin access to view the assigner dashboard.", ephemeral=True)
            return
        await self._render(interaction, mode="assigner_vertical")

    @discord.ui.button(label="Show Done + Archived", style=discord.ButtonStyle.success, row=2, custom_id="taskbot:dashboard_toggle_closed")
    async def toggle_closed(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._render(interaction, show_closed=not self.show_closed)


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


def template_list_content(templates: list[dict]) -> str:
    lines = [f"`{t['name']}` — {t.get('title') or 'Untitled'}" for t in templates[:20]]
    return "**Templates**\n" + "\n".join(lines)


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

    @discord.ui.button(label="Back to Template List", style=discord.ButtonStyle.secondary)
    async def back_to_list(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        templates = list_templates(int(self.template["guild_id"]), int(self.template["owner_id"]))
        if not templates:
            await interaction.response.edit_message(content="You have no templates yet.", embed=None, view=None)
            return
        await interaction.response.edit_message(
            content=template_list_content(templates),
            embed=None,
            view=TemplateListView(self.bot, int(self.template["guild_id"]), int(self.template["owner_id"]), templates),
        )

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.success)
    async def use_template(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Choose dropdown values, then press **Next: engine/tools** and **Continue to form**.", ephemeral=True, embed=create_guidance_embed(stage="main"), view=TaskCreateWizardView(self.bot, interaction.user.id, template=self.template))

    @discord.ui.button(label="Edit Template", style=discord.ButtonStyle.primary)
    async def edit_template(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            "Edit the dropdown/category values first, then press **Next: engine/tools** and **Continue to form** to edit the text fields.",
            ephemeral=True,
            embed=create_guidance_embed(stage="main"),
            view=TaskCreateWizardView(self.bot, interaction.user.id, template=self.template, mode="template_edit"),
        )

    @discord.ui.button(label="Delete Template", style=discord.ButtonStyle.danger)
    async def delete_template_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ok = delete_template(int(self.template["guild_id"]), int(self.template["owner_id"]), self.template["name"])
        await interaction.response.send_message(f"Deleted `{self.template['name']}`." if ok else "Template was already deleted.", ephemeral=True)


class TemplateListView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, owner_id: int, templates: list[dict]) -> None:
        super().__init__(timeout=900)
        self.bot = bot
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.templates = {str(t["name"]): t for t in templates[:25]}
        self.selected_name = next(iter(self.templates), "")
        self.add_item(TemplatePicker(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the template owner can use this list.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="View selected template", style=discord.ButtonStyle.primary)
    async def view_selected(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        template = self.templates.get(self.selected_name)
        if not template:
            await interaction.response.send_message("Pick a template first.", ephemeral=True)
            return
        await interaction.response.edit_message(content=None, embed=template_embed(template), view=TemplateDetailView(self.bot, template))


class TemplatePicker(discord.ui.Select):
    def __init__(self, parent: TemplateListView) -> None:
        self.parent_view = parent
        options = [
            discord.SelectOption(
                label=str(t["name"])[:100],
                value=str(t["name"]),
                description=((t.get("title") or "Untitled")[:100]),
            )
            for t in parent.templates.values()
        ]
        super().__init__(placeholder="Choose a template to view/edit", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.selected_name = self.values[0]
        await interaction.response.defer(ephemeral=True)
