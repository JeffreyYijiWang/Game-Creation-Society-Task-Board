from __future__ import annotations

import discord
from discord.ext import commands

from taskbot.access import can_manage_task
from taskbot.db import add_event, create_task_record, get_task_by_thread, update_task, upsert_profile, upsert_template
from taskbot.embeds import task_embed, template_embed
from taskbot.forum import get_task_forum, matching_forum_tags, sync_discord_task, task_thread_title
from taskbot.utils import (
    normalize_dev_environments,
    normalize_game_engine,
    normalize_game_programs,
    normalize_job_roles,
    normalize_priority,
    normalize_task_types,
    parse_due_date_to_iso,
)
from taskbot.views import TaskControls


class CommentModal(discord.ui.Modal, title="Add Task Comment"):
    comment = discord.ui.TextInput(label="Comment", placeholder="Write a short update or note...", style=discord.TextStyle.paragraph, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("Comments only work inside a task thread.", ephemeral=True)
            return
        task = get_task_by_thread(interaction.channel.id)
        if not task:
            await interaction.response.send_message("I could not find a task record for this thread.", ephemeral=True)
            return
        comment_text = str(self.comment.value).strip()
        add_event(task["id"], interaction.user.id, "comment", comment_text)
        await interaction.channel.send(f"**Comment from {interaction.user.mention}:**\n{comment_text}")
        await interaction.response.send_message("Comment added.", ephemeral=True)


class ProfileEditModal(discord.ui.Modal, title="Edit Your Task Profile"):
    display_name = discord.ui.TextInput(label="Display name", required=False, max_length=80)
    bio = discord.ui.TextInput(label="Short bio", style=discord.TextStyle.paragraph, required=False, max_length=700)
    skills = discord.ui.TextInput(label="Skills, comma-separated", required=False, max_length=300)
    availability_and_roles = discord.ui.TextInput(label="Availability and preferred roles", placeholder="availability: weekends\nroles: Programmer, UI Artist", style=discord.TextStyle.paragraph, required=False, max_length=700)
    links_env_programs = discord.ui.TextInput(label="Links, OS, programs/tools", placeholder="portfolio: https://...\nimage: https://...\nenv: Windows, Mac\nprograms: Unity, Blender, Figma", style=discord.TextStyle.paragraph, required=False, max_length=700)

    def __init__(self, *, guild_id: int, user_id: int, existing: dict | None = None) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        existing = existing or {}
        self.display_name.default = existing.get("display_name", "")
        self.bio.default = existing.get("bio", "")
        self.skills.default = existing.get("skills", "")
        self.availability_and_roles.default = f"availability: {existing.get('availability', '')}\nroles: {existing.get('preferred_roles', '')}".strip()
        self.links_env_programs.default = f"portfolio: {existing.get('portfolio_url', '')}\nimage: {existing.get('profile_image_url', '')}\nenv: {existing.get('dev_environments', '')}\nprograms: {existing.get('game_programs', '')}".strip()

    @staticmethod
    def parse_block(raw: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in raw.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                result[key.strip().lower()] = value.strip()
        return result

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Profiles only work inside a server.", ephemeral=True)
            return
        ar = self.parse_block(str(self.availability_and_roles.value))
        lep = self.parse_block(str(self.links_env_programs.value))
        upsert_profile(
            guild_id=self.guild_id,
            user_id=self.user_id,
            display_name=str(self.display_name.value).strip() or interaction.user.display_name,
            bio=str(self.bio.value),
            skills=str(self.skills.value),
            portfolio_url=lep.get("portfolio", ""),
            availability=ar.get("availability", ""),
            preferred_roles=ar.get("roles", ""),
            dev_environments=normalize_dev_environments(lep.get("env", "")),
            game_programs=normalize_game_programs(lep.get("programs", "")),
            profile_image_url=lep.get("image", ""),
        )
        await interaction.response.send_message("Your task profile card was updated. Continue with the task action when you are ready.", ephemeral=True)


class TaskCreateModal(discord.ui.Modal, title="Create Recruitment / Task Post"):
    task_title = discord.ui.TextInput(label="Task title", placeholder="Need a UI artist for menu polish", max_length=100)
    description = discord.ui.TextInput(label="Description", placeholder="What needs to be done? What skill level is needed?", style=discord.TextStyle.paragraph, required=False, max_length=1000)
    priority = discord.ui.TextInput(label="Priority: Low, Medium, High, or Urgent", placeholder="High", default="Medium", max_length=20)
    due_date = discord.ui.TextInput(label="Due date, best as YYYY-MM-DD", placeholder="2026-05-30", required=False, max_length=80)
    links_programs = discord.ui.TextInput(
        label="Links, tools, optional custom tags",
        placeholder="links: https://example.com/spec, https://example.com/ref\nprograms: Unity, Blender, Figma\ncustom_tags: puzzle, game-jam",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(
        self,
        bot: commands.Bot,
        *,
        thumbnail_url: str = "",
        positions_needed: int = 1,
        job_role: str = "Programmer",
        dev_environment: str = "Windows",
        game_engine: str = "Unity",
        custom_game_engine: str = "",
        game_programs: str = "",
        task_type: str = "Feature",
        template: dict | None = None,
    ) -> None:
        super().__init__()
        self.bot = bot
        self.thumbnail_url = thumbnail_url or (template or {}).get("thumbnail_url", "")
        self.positions_needed = positions_needed or int((template or {}).get("positions_needed", 1))
        self.job_role = normalize_job_roles(job_role or (template or {}).get("job_role", "Programmer"))
        self.dev_environment = normalize_dev_environments(dev_environment or (template or {}).get("dev_environment", "Windows"))
        self.game_engine = normalize_game_engine(game_engine or (template or {}).get("game_engine", "Unity"))
        self.custom_game_engine = custom_game_engine or (template or {}).get("custom_game_engine", "")
        self.game_programs = normalize_game_programs(game_programs or (template or {}).get("game_programs", ""))
        self.task_type = normalize_task_types(task_type or (template or {}).get("task_type", "Feature"))
        self.task_title.default = (template or {}).get("title", "")
        self.description.default = (template or {}).get("description", "")
        self.priority.default = (template or {}).get("priority", "Medium")
        self.due_date.default = (template or {}).get("due_date", "")
        self.links_programs.default = f"links: {(template or {}).get('resource_links', '')}\nprograms: {self.game_programs}\ncustom_tags: {(template or {}).get('tags', '')}".strip()

    @staticmethod
    def parse_tags_links_programs(raw: str) -> tuple[str, str, str]:
        tags: list[str] = []
        links: list[str] = []
        programs: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if lower.startswith("custom_tags:"):
                tags.extend([x.strip() for x in stripped.split(":", 1)[1].split(",") if x.strip()])
            elif lower.startswith("tags:"):
                # Kept for backwards compatibility with old templates.
                tags.extend([x.strip() for x in stripped.split(":", 1)[1].split(",") if x.strip()])
            elif lower.startswith("links:"):
                links.extend([x.strip() for x in stripped.split(":", 1)[1].replace("\n", ",").split(",") if x.strip()])
            elif lower.startswith("programs:") or lower.startswith("tools:"):
                programs.extend([x.strip() for x in stripped.split(":", 1)[1].split(",") if x.strip()])
            elif stripped.startswith("http://") or stripped.startswith("https://"):
                links.append(stripped)
            else:
                tags.extend([x.strip() for x in stripped.split(",") if x.strip()])
        return ", ".join(tags), "\n".join(links), normalize_game_programs(programs)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Tasks can only be created inside a server.", ephemeral=True)
            return
        title = str(self.task_title.value).strip()
        if not title:
            await interaction.response.send_message("Task title cannot be empty.", ephemeral=True)
            return
        try:
            due_date = parse_due_date_to_iso(str(self.due_date.value))
        except ValueError:
            await interaction.response.send_message("I could not parse the due date. Use `YYYY-MM-DD`.", ephemeral=True)
            return
        tags, links, programs = self.parse_tags_links_programs(str(self.links_programs.value))
        game_programs = programs or self.game_programs
        await interaction.response.defer(ephemeral=True)
        forum = await get_task_forum(self.bot)
        task = create_task_record(
            guild_id=interaction.guild.id,
            forum_channel_id=forum.id,
            title=title,
            description=str(self.description.value).strip(),
            priority=str(self.priority.value).strip(),
            creator_id=interaction.user.id,
            due_date=due_date,
            tags=tags,
            resource_links=links,
            thumbnail_url=self.thumbnail_url,
            positions_needed=self.positions_needed,
            job_role=self.job_role,
            dev_environment=self.dev_environment,
            game_engine=self.game_engine,
            custom_game_engine=self.custom_game_engine,
            game_programs=game_programs,
            task_type=self.task_type,
        )
        content = f"Task #{task['id']} created by {interaction.user.mention}."
        if self.thumbnail_url:
            content += f"\nThumbnail / gallery image: {self.thumbnail_url}"
        created = await forum.create_thread(name=task_thread_title(task), content=content, embed=task_embed(task), view=TaskControls(), applied_tags=matching_forum_tags(forum, task))
        updated = update_task(task["id"], interaction.user.id, "discord_thread_created", thread_id=created.thread.id, message_id=created.message.id)
        if updated:
            await sync_discord_task(self.bot, updated)
            from taskbot.notifications import notify_new_task_subscribers
            await notify_new_task_subscribers(self.bot, updated)
        await interaction.followup.send(f"Created task #{task['id']}: {created.thread.mention}\nTo add images/docs/files, use `/task attach task_id:{task['id']}`.", ephemeral=True)


class TaskEditModal(discord.ui.Modal, title="Edit Existing Task"):
    task_title = discord.ui.TextInput(label="Task title", max_length=100)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=False, max_length=1000)
    priority_due = discord.ui.TextInput(label="Priority and due date", placeholder="priority: High\ndue: 2026-05-30", required=False, style=discord.TextStyle.paragraph, max_length=300)
    categories = discord.ui.TextInput(
        label="Capacity, type, roles, OS, engine, image",
        placeholder="positions: 3\ntype: Bug Fix, Code\nroles: Programmer, UI Artist\nenv: Windows, Mac\nengine: Unity\ncustom_engine:\nthumbnail: https://...",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=900,
    )
    links_programs = discord.ui.TextInput(label="Links, programs/tools, optional tags", placeholder="links: https://...\nprograms: Unity, Blender\ncustom_tags: puzzle, jam", required=False, style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, bot: commands.Bot, task: dict, *, thumbnail_url: str = "") -> None:
        super().__init__()
        self.bot = bot
        self.task = task
        self.new_thumbnail_url = thumbnail_url
        self.task_title.default = task.get("title", "")
        self.description.default = task.get("description", "")
        self.priority_due.default = f"priority: {task.get('priority', 'Medium')}\ndue: {task.get('due_date', '')}".strip()
        self.categories.default = (
            f"positions: {task.get('positions_needed', 1)}\n"
            f"type: {task.get('task_type', '')}\n"
            f"roles: {task.get('job_role', '')}\n"
            f"env: {task.get('dev_environment', '')}\n"
            f"engine: {task.get('game_engine', '')}\n"
            f"custom_engine: {task.get('custom_game_engine', '')}\n"
            f"thumbnail: {thumbnail_url or task.get('thumbnail_url', '')}"
        ).strip()
        self.links_programs.default = f"links: {task.get('resource_links', '')}\nprograms: {task.get('game_programs', '')}\ncustom_tags: {task.get('tags', '')}".strip()

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not can_manage_task(interaction.user, self.task):
            await interaction.response.send_message("Only admins or the task assigner who created this task can edit it.", ephemeral=True)
            return
        pd = ProfileEditModal.parse_block(str(self.priority_due.value))
        cat = ProfileEditModal.parse_block(str(self.categories.value))
        try:
            due_date = parse_due_date_to_iso(pd.get("due", self.task.get("due_date", "")))
        except ValueError:
            await interaction.response.send_message("I could not parse the due date. Use `YYYY-MM-DD`.", ephemeral=True)
            return
        tags, links, programs = TaskCreateModal.parse_tags_links_programs(str(self.links_programs.value))
        thumbnail_value = self.new_thumbnail_url or cat.get("thumbnail", self.task.get("thumbnail_url", ""))
        fields = {
            "title": str(self.task_title.value).strip() or self.task.get("title", ""),
            "description": str(self.description.value).strip(),
            "priority": normalize_priority(pd.get("priority", self.task.get("priority", "Medium"))),
            "due_date": due_date,
            "tags": tags,
            "task_type": normalize_task_types(cat.get("type", self.task.get("task_type", "Feature"))),
            "resource_links": links,
            "thumbnail_url": thumbnail_value.strip(),
            "positions_needed": max(1, int(cat.get("positions", self.task.get("positions_needed", 1)) or 1)),
            "job_role": normalize_job_roles(cat.get("roles", self.task.get("job_role", "Programmer"))),
            "dev_environment": normalize_dev_environments(cat.get("env", self.task.get("dev_environment", "Windows"))),
            "game_engine": normalize_game_engine(cat.get("engine", self.task.get("game_engine", "Other"))),
            "custom_game_engine": cat.get("custom_engine", self.task.get("custom_game_engine", "")),
            "game_programs": programs or self.task.get("game_programs", ""),
        }
        await interaction.response.defer(ephemeral=True)
        updated = update_task(self.task["id"], interaction.user.id, "edited", **fields)
        if updated:
            await sync_discord_task(self.bot, updated)
        await interaction.followup.send(f"Updated task #{self.task['id']}.", ephemeral=True)


class TemplateSaveModal(discord.ui.Modal, title="Save / Edit Task Template"):
    task_title = discord.ui.TextInput(label="Template title", placeholder="Need a programmer for gameplay prototype", max_length=100)
    description = discord.ui.TextInput(label="Template description", style=discord.TextStyle.paragraph, required=False, max_length=1000)
    priority = discord.ui.TextInput(label="Priority", placeholder="Medium", default="Medium", max_length=20)
    due_date = discord.ui.TextInput(label="Due date default", placeholder="Optional", required=False, max_length=80)
    links_programs = discord.ui.TextInput(label="Default links, programs/tools, optional tags", placeholder="links: https://example.com\nprograms: Unity, Blender\ncustom_tags: prototype, short-term", style=discord.TextStyle.paragraph, required=False, max_length=1000)

    def __init__(
        self,
        *,
        guild_id: int,
        owner_id: int,
        name: str,
        thumbnail_url: str = "",
        positions_needed: int = 1,
        job_role: str = "Programmer",
        dev_environment: str = "Windows",
        game_engine: str = "Unity",
        custom_game_engine: str = "",
        game_programs: str = "",
        task_type: str = "Feature",
        existing: dict | None = None,
    ) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.name = name
        self.thumbnail_url = thumbnail_url or (existing or {}).get("thumbnail_url", "")
        self.positions_needed = positions_needed or int((existing or {}).get("positions_needed", 1))
        self.job_role = normalize_job_roles(job_role or (existing or {}).get("job_role", "Programmer"))
        self.dev_environment = normalize_dev_environments(dev_environment or (existing or {}).get("dev_environment", "Windows"))
        self.game_engine = normalize_game_engine(game_engine or (existing or {}).get("game_engine", "Unity"))
        self.custom_game_engine = custom_game_engine or (existing or {}).get("custom_game_engine", "")
        self.game_programs = normalize_game_programs(game_programs or (existing or {}).get("game_programs", ""))
        self.task_type = normalize_task_types(task_type or (existing or {}).get("task_type", "Feature"))
        self.task_title.default = (existing or {}).get("title", "")
        self.description.default = (existing or {}).get("description", "")
        self.priority.default = (existing or {}).get("priority", "Medium")
        self.due_date.default = (existing or {}).get("due_date", "")
        self.links_programs.default = f"links: {(existing or {}).get('resource_links', '')}\nprograms: {self.game_programs}\ncustom_tags: {(existing or {}).get('tags', '')}".strip()

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            due_date = parse_due_date_to_iso(str(self.due_date.value))
        except ValueError:
            await interaction.response.send_message("Could not parse due date. Use `YYYY-MM-DD` or leave it blank.", ephemeral=True)
            return
        tags, links, programs = TaskCreateModal.parse_tags_links_programs(str(self.links_programs.value))
        template = upsert_template(
            guild_id=self.guild_id,
            owner_id=self.owner_id,
            name=self.name,
            title=str(self.task_title.value),
            description=str(self.description.value),
            priority=str(self.priority.value),
            due_date=due_date,
            tags=tags,
            task_type=self.task_type,
            resource_links=links,
            thumbnail_url=self.thumbnail_url,
            positions_needed=self.positions_needed,
            job_role=self.job_role,
            dev_environment=self.dev_environment,
            game_engine=self.game_engine,
            custom_game_engine=self.custom_game_engine,
            game_programs=programs or self.game_programs,
        )
        from taskbot.views import TemplateDetailView
        await interaction.response.send_message(embed=template_embed(template), view=TemplateDetailView(interaction.client, template), ephemeral=True)  # type: ignore[arg-type]
