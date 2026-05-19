from __future__ import annotations

import discord
from discord.ext import commands

from taskbot.db import add_event, create_task_record, get_task_by_thread, update_task, upsert_profile, upsert_template
from taskbot.embeds import task_embed
from taskbot.forum import get_task_forum, matching_forum_tags, sync_discord_task, task_thread_title
from taskbot.utils import normalize_dev_environments, parse_due_date_to_iso
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
    links_and_env = discord.ui.TextInput(label="Portfolio/profile image/dev env", placeholder="portfolio: https://...\nimage: https://...\nenv: Windows, Mac", style=discord.TextStyle.paragraph, required=False, max_length=700)

    def __init__(self, *, guild_id: int, user_id: int, existing: dict | None = None) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        existing = existing or {}
        self.display_name.default = existing.get("display_name", "")
        self.bio.default = existing.get("bio", "")
        self.skills.default = existing.get("skills", "")
        self.availability_and_roles.default = f"availability: {existing.get('availability', '')}\nroles: {existing.get('preferred_roles', '')}".strip()
        self.links_and_env.default = f"portfolio: {existing.get('portfolio_url', '')}\nimage: {existing.get('profile_image_url', '')}\nenv: {existing.get('dev_environments', '')}".strip()

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
        le = self.parse_block(str(self.links_and_env.value))
        upsert_profile(
            guild_id=self.guild_id,
            user_id=self.user_id,
            display_name=str(self.display_name.value).strip() or interaction.user.display_name,
            bio=str(self.bio.value),
            skills=str(self.skills.value),
            portfolio_url=le.get("portfolio", ""),
            availability=ar.get("availability", ""),
            preferred_roles=ar.get("roles", ""),
            dev_environments=normalize_dev_environments(le.get("env", "")),
            profile_image_url=le.get("image", ""),
        )
        await interaction.response.send_message("Your task profile card was updated.", ephemeral=True)


class TaskCreateModal(discord.ui.Modal, title="Create Recruitment / Task Post"):
    task_title = discord.ui.TextInput(label="Task title", placeholder="Need a UI artist for menu polish", max_length=100)
    description = discord.ui.TextInput(label="Description", placeholder="What needs to be done? What skill level is needed?", style=discord.TextStyle.paragraph, required=False, max_length=1000)
    priority = discord.ui.TextInput(label="Priority: Low, Medium, High, or Urgent", placeholder="High", default="Medium", max_length=20)
    due_date = discord.ui.TextInput(label="Due date, best as YYYY-MM-DD", placeholder="2026-05-30", required=False, max_length=80)
    tags_and_links = discord.ui.TextInput(label="Tags and resource links", placeholder="tags: puzzle, jam, short-term\nlinks: https://example.com/spec", style=discord.TextStyle.paragraph, required=False, max_length=1000)

    def __init__(self, bot: commands.Bot, *, thumbnail_url: str = "", positions_needed: int = 1, job_role: str = "Programmer", dev_environment: str = "Windows", game_engine: str = "Unity", custom_game_engine: str = "", template: dict | None = None) -> None:
        super().__init__()
        self.bot = bot
        self.thumbnail_url = thumbnail_url or (template or {}).get("thumbnail_url", "")
        self.positions_needed = positions_needed or int((template or {}).get("positions_needed", 1))
        self.job_role = job_role or (template or {}).get("job_role", "Programmer")
        self.dev_environment = normalize_dev_environments(dev_environment or (template or {}).get("dev_environment", "Windows"))
        self.game_engine = game_engine or (template or {}).get("game_engine", "Unity")
        self.custom_game_engine = custom_game_engine or (template or {}).get("custom_game_engine", "")
        self.task_title.default = (template or {}).get("title", "")
        self.description.default = (template or {}).get("description", "")
        self.priority.default = (template or {}).get("priority", "Medium")
        self.due_date.default = (template or {}).get("due_date", "")
        self.tags_and_links.default = f"tags: {(template or {}).get('tags', '')}\nlinks: {(template or {}).get('resource_links', '')}".strip()

    @staticmethod
    def parse_tags_and_links(raw: str) -> tuple[str, str]:
        tags: list[str] = []
        links: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if lower.startswith("tags:"):
                tags.extend([x.strip() for x in stripped[5:].split(",") if x.strip()])
            elif lower.startswith("links:"):
                links.append(stripped[6:].strip())
            elif stripped.startswith("http://") or stripped.startswith("https://"):
                links.append(stripped)
            else:
                tags.extend([x.strip() for x in stripped.split(",") if x.strip()])
        return ", ".join(tags), "\n".join(links)

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
        tags, links = self.parse_tags_and_links(str(self.tags_and_links.value))
        await interaction.response.defer(ephemeral=True)
        forum = await get_task_forum(self.bot)
        task = create_task_record(
            guild_id=interaction.guild.id, forum_channel_id=forum.id, title=title, description=str(self.description.value).strip(),
            priority=str(self.priority.value).strip(), creator_id=interaction.user.id, due_date=due_date, tags=tags, resource_links=links,
            thumbnail_url=self.thumbnail_url, positions_needed=self.positions_needed, job_role=self.job_role,
            dev_environment=self.dev_environment, game_engine=self.game_engine, custom_game_engine=self.custom_game_engine,
        )
        content = f"Task #{task['id']} created by {interaction.user.mention}."
        if self.thumbnail_url:
            content += f"\nThumbnail / gallery image: {self.thumbnail_url}"
        created = await forum.create_thread(name=task_thread_title(task), content=content, embed=task_embed(task), view=TaskControls(), applied_tags=matching_forum_tags(forum, task))
        updated = update_task(task["id"], interaction.user.id, "discord_thread_created", thread_id=created.thread.id, message_id=created.message.id)
        if updated:
            await sync_discord_task(self.bot, updated)
        await interaction.followup.send(f"Created task #{task['id']}: {created.thread.mention}\nTo add images/docs/files, use `/task attach task_id:{task['id']}`.", ephemeral=True)


class TemplateSaveModal(discord.ui.Modal, title="Save / Edit Task Template"):
    task_title = discord.ui.TextInput(label="Template title", placeholder="Need a programmer for gameplay prototype", max_length=100)
    description = discord.ui.TextInput(label="Template description", style=discord.TextStyle.paragraph, required=False, max_length=1000)
    priority = discord.ui.TextInput(label="Priority", placeholder="Medium", default="Medium", max_length=20)
    due_date = discord.ui.TextInput(label="Due date default", placeholder="Optional", required=False, max_length=80)
    tags_and_links = discord.ui.TextInput(label="Default tags and links", placeholder="tags: prototype, short-term\nlinks: https://example.com", style=discord.TextStyle.paragraph, required=False, max_length=1000)

    def __init__(self, *, guild_id: int, owner_id: int, name: str, thumbnail_url: str = "", positions_needed: int = 1, job_role: str = "Programmer", dev_environment: str = "Windows", game_engine: str = "Unity", custom_game_engine: str = "", existing: dict | None = None) -> None:
        super().__init__()
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.name = name
        self.thumbnail_url = thumbnail_url or (existing or {}).get("thumbnail_url", "")
        self.positions_needed = positions_needed or int((existing or {}).get("positions_needed", 1))
        self.job_role = job_role or (existing or {}).get("job_role", "Programmer")
        self.dev_environment = normalize_dev_environments(dev_environment or (existing or {}).get("dev_environment", "Windows"))
        self.game_engine = game_engine or (existing or {}).get("game_engine", "Unity")
        self.custom_game_engine = custom_game_engine or (existing or {}).get("custom_game_engine", "")
        self.task_title.default = (existing or {}).get("title", "")
        self.description.default = (existing or {}).get("description", "")
        self.priority.default = (existing or {}).get("priority", "Medium")
        self.due_date.default = (existing or {}).get("due_date", "")
        self.tags_and_links.default = f"tags: {(existing or {}).get('tags', '')}\nlinks: {(existing or {}).get('resource_links', '')}".strip()

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            due_date = parse_due_date_to_iso(str(self.due_date.value))
        except ValueError:
            await interaction.response.send_message("Could not parse due date. Use `YYYY-MM-DD` or leave it blank.", ephemeral=True)
            return
        tags, links = TaskCreateModal.parse_tags_and_links(str(self.tags_and_links.value))
        upsert_template(
            guild_id=self.guild_id, owner_id=self.owner_id, name=self.name, title=str(self.task_title.value), description=str(self.description.value),
            priority=str(self.priority.value), due_date=due_date, tags=tags, resource_links=links, thumbnail_url=self.thumbnail_url,
            positions_needed=self.positions_needed, job_role=self.job_role, dev_environment=self.dev_environment,
            game_engine=self.game_engine, custom_game_engine=self.custom_game_engine,
        )
        await interaction.response.send_message(f"Saved template `{self.name}`.", ephemeral=True)
