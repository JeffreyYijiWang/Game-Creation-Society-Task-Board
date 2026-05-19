"""
Discord Kanban Bot — Discord-native task board MVP

Features:
- /task create opens a Discord modal form
- Creates one Forum Channel post per task
- Stores tasks in SQLite for search/archive/restore
- Uses buttons for Claim, In Progress, Review, Done, Comment, Archive
- Uses existing Discord Forum tags when names match status/priority/custom tags

Setup:
1. pip install -U discord.py python-dotenv
2. Create a Discord bot in the Discord Developer Portal.
3. Enable the bot/application permissions needed for slash commands and channel/thread management.
4. Create a Discord Forum Channel for tasks.
5. Add forum tags manually, for example:
   To Do, In Progress, Review, Done, Archived, Low, Medium, High, Urgent, Bug, Feature, Art, Code
6. Create a .env file:
   DISCORD_TOKEN=your_bot_token_here
   TASK_FORUM_CHANNEL_ID=123456789012345678
   GUILD_ID=123456789012345678   # optional, but useful for fast slash-command syncing while developing
7. python discord_kanban_bot.py
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional, Iterable

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TASK_FORUM_CHANNEL_ID = int(os.getenv("TASK_FORUM_CHANNEL_ID", "0"))
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None
DB_PATH = os.getenv("TASKBOT_DB", "taskbot.sqlite3")

STATUS_CHOICES = ["To Do", "In Progress", "Review", "Done", "Archived"]
PRIORITY_CHOICES = ["Low", "Medium", "High", "Urgent"]

STATUS_COLORS = {
    "To Do": discord.Color.light_grey(),
    "In Progress": discord.Color.blurple(),
    "Review": discord.Color.gold(),
    "Done": discord.Color.green(),
    "Archived": discord.Color.dark_grey(),
}


def now_iso() -> str:
    return discord.utils.utcnow().isoformat()


def clean_csv_tags(raw: str | None) -> str:
    if not raw:
        return ""
    tags: list[str] = []
    seen: set[str] = set()
    for part in raw.replace("#", "").split(","):
        tag = part.strip()
        if not tag:
            continue
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            tags.append(tag)
    return ", ".join(tags)


def split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def normalize_status(status: str | None) -> str:
    if not status:
        return "To Do"
    for s in STATUS_CHOICES:
        if status.strip().lower() == s.lower():
            return s
    return "To Do"


def normalize_priority(priority: str | None) -> str:
    if not priority:
        return "Medium"
    for p in PRIORITY_CHOICES:
        if priority.strip().lower() == p.lower():
            return p
    return "Medium"


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                forum_channel_id INTEGER NOT NULL,
                thread_id INTEGER,
                message_id INTEGER,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'To Do',
                priority TEXT NOT NULL DEFAULT 'Medium',
                assignee_id INTEGER,
                creator_id INTEGER NOT NULL,
                due_date TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                actor_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                old_value TEXT DEFAULT '',
                new_value TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """
        )
        conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> Optional[dict]:
    return dict(row) if row else None


def create_task_record(
    *,
    guild_id: int,
    forum_channel_id: int,
    title: str,
    description: str,
    priority: str,
    creator_id: int,
    due_date: str,
    tags: str,
) -> dict:
    timestamp = now_iso()
    with connect_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (
                guild_id, forum_channel_id, title, description, status,
                priority, creator_id, due_date, tags, archived,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                guild_id,
                forum_channel_id,
                title,
                description,
                "To Do",
                normalize_priority(priority),
                creator_id,
                due_date,
                clean_csv_tags(tags),
                timestamp,
                timestamp,
            ),
        )
        task_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO task_events (task_id, actor_id, event_type, new_value, created_at)
            VALUES (?, ?, 'created', ?, ?)
            """,
            (task_id, creator_id, title, timestamp),
        )
        conn.commit()
        return get_task(task_id)  # type: ignore[return-value]


def get_task(task_id: int) -> Optional[dict]:
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row_to_dict(row)


def get_task_by_thread(thread_id: int) -> Optional[dict]:
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE thread_id = ?", (thread_id,)).fetchone()
    return row_to_dict(row)


def update_task(task_id: int, actor_id: int, event_type: str, **fields) -> Optional[dict]:
    if not fields:
        return get_task(task_id)

    old_task = get_task(task_id)
    if not old_task:
        return None

    fields["updated_at"] = now_iso()
    assignments = ", ".join(f"{key} = ?" for key in fields.keys())
    values = list(fields.values()) + [task_id]

    with connect_db() as conn:
        conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", values)
        conn.execute(
            """
            INSERT INTO task_events (task_id, actor_id, event_type, old_value, new_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                actor_id,
                event_type,
                str({k: old_task.get(k) for k in fields.keys()}),
                str(fields),
                now_iso(),
            ),
        )
        conn.commit()
    return get_task(task_id)


def add_event(task_id: int, actor_id: int, event_type: str, new_value: str) -> None:
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO task_events (task_id, actor_id, event_type, new_value, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, actor_id, event_type, new_value, now_iso()),
        )
        conn.commit()


def search_tasks(
    *,
    guild_id: int,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    tag: Optional[str] = None,
    assignee_id: Optional[int] = None,
    include_archived: bool = False,
    limit: int = 10,
) -> list[dict]:
    where = ["guild_id = ?"]
    params: list[object] = [guild_id]

    if not include_archived:
        where.append("archived = 0")
    if status:
        where.append("LOWER(status) = LOWER(?)")
        params.append(normalize_status(status))
    if priority:
        where.append("LOWER(priority) = LOWER(?)")
        params.append(normalize_priority(priority))
    if tag:
        where.append("LOWER(tags) LIKE LOWER(?)")
        params.append(f"%{tag.strip()}%")
    if assignee_id:
        where.append("assignee_id = ?")
        params.append(assignee_id)

    params.append(limit)

    query = f"""
        SELECT * FROM tasks
        WHERE {' AND '.join(where)}
        ORDER BY archived ASC, updated_at DESC
        LIMIT ?
    """
    with connect_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def task_thread_title(task: dict) -> str:
    archive_prefix = "[ARCHIVED] " if task.get("archived") else ""
    return f"{archive_prefix}#{task['id']} [{task['priority']}] {task['title']}"[:100]


def task_embed(task: dict) -> discord.Embed:
    status = task["status"]
    assignee = f"<@{task['assignee_id']}>" if task.get("assignee_id") else "Unassigned"
    due_date = task.get("due_date") or "No due date"
    tags = task.get("tags") or "None"

    embed = discord.Embed(
        title=f"Task #{task['id']}: {task['title']}",
        description=task.get("description") or "No description provided.",
        color=STATUS_COLORS.get(status, discord.Color.blurple()),
    )
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Priority", value=task["priority"], inline=True)
    embed.add_field(name="Assignee", value=assignee, inline=True)
    embed.add_field(name="Due Date", value=due_date, inline=True)
    embed.add_field(name="Tags", value=tags, inline=False)
    embed.add_field(name="Created By", value=f"<@{task['creator_id']}>", inline=True)
    embed.set_footer(text=f"Updated: {task['updated_at']}")
    return embed


def matching_forum_tags(forum: discord.ForumChannel, task: dict) -> list[discord.ForumTag]:
    """Apply Discord Forum tags only if they already exist in the forum settings."""
    wanted_names = [task["status"], task["priority"], *split_tags(task.get("tags"))]
    by_name = {tag.name.lower(): tag for tag in forum.available_tags}

    result: list[discord.ForumTag] = []
    seen: set[int] = set()
    for name in wanted_names:
        forum_tag = by_name.get(name.lower())
        if forum_tag and forum_tag.id not in seen:
            seen.add(forum_tag.id)
            result.append(forum_tag)
    return result[:5]  # Discord forum posts have a small applied-tag limit.


async def get_task_forum(bot: commands.Bot) -> discord.ForumChannel:
    channel = bot.get_channel(TASK_FORUM_CHANNEL_ID)
    if channel is None:
        channel = await bot.fetch_channel(TASK_FORUM_CHANNEL_ID)
    if not isinstance(channel, discord.ForumChannel):
        raise RuntimeError("TASK_FORUM_CHANNEL_ID must point to a Discord Forum Channel.")
    return channel


async def sync_discord_task(bot: commands.Bot, task: dict) -> None:
    """Update the Discord thread title, tags, starter message embed, and archive state."""
    if not task.get("thread_id"):
        return

    forum = await get_task_forum(bot)

    thread = bot.get_channel(task["thread_id"])
    if thread is None:
        thread = await bot.fetch_channel(task["thread_id"])
    if not isinstance(thread, discord.Thread):
        return

    try:
        await thread.edit(
            name=task_thread_title(task),
            applied_tags=matching_forum_tags(forum, task),
        )
    except discord.HTTPException:
        # The task still works in SQLite even if Discord tag/title sync fails.
        pass

    if task.get("message_id"):
        try:
            starter_message = await thread.fetch_message(task["message_id"])
            await starter_message.edit(embed=task_embed(task), view=TaskControls())
        except discord.HTTPException:
            pass

    if task.get("archived"):
        try:
            await thread.edit(archived=True, locked=True)
        except discord.HTTPException:
            pass
    else:
        try:
            await thread.edit(archived=False, locked=False)
        except discord.HTTPException:
            pass


class CommentModal(discord.ui.Modal, title="Add Task Comment"):
    comment = discord.ui.TextInput(
        label="Comment",
        placeholder="Write a short update or note...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

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


class TaskControls(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def get_task_from_interaction(self, interaction: discord.Interaction) -> Optional[dict]:
        if isinstance(interaction.channel, discord.Thread):
            return get_task_by_thread(interaction.channel.id)
        if interaction.message:
            with connect_db() as conn:
                row = conn.execute(
                    "SELECT * FROM tasks WHERE message_id = ?",
                    (interaction.message.id,),
                ).fetchone()
            return row_to_dict(row)
        return None

    async def change_status(self, interaction: discord.Interaction, status: str, archived: int = 0) -> None:
        task = await self.get_task_from_interaction(interaction)
        if not task:
            await interaction.response.send_message("Could not find this task in the database.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        updated = update_task(
            task["id"],
            interaction.user.id,
            "status_changed",
            status=status,
            archived=archived,
        )
        if updated:
            await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
            await interaction.followup.send(f"Task #{updated['id']} moved to **{status}**.", ephemeral=True)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, custom_id="taskbot:claim", row=0)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        task = await self.get_task_from_interaction(interaction)
        if not task:
            await interaction.response.send_message("Could not find this task in the database.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        updated = update_task(
            task["id"],
            interaction.user.id,
            "claimed",
            assignee_id=interaction.user.id,
        )
        if updated:
            await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
            await interaction.followup.send(f"You claimed task #{updated['id']}.", ephemeral=True)

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
        await interaction.response.send_modal(CommentModal())

    @discord.ui.button(label="Archive", style=discord.ButtonStyle.danger, custom_id="taskbot:archive", row=1)
    async def archive(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.change_status(interaction, "Archived", archived=1)


class TaskCreateModal(discord.ui.Modal, title="Create New Task"):
    task_title = discord.ui.TextInput(
        label="Task title",
        placeholder="Fix renderer bug",
        max_length=100,
    )
    description = discord.ui.TextInput(
        label="Description",
        placeholder="What needs to be done?",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )
    priority = discord.ui.TextInput(
        label="Priority: Low, Medium, High, or Urgent",
        placeholder="High",
        default="Medium",
        max_length=20,
    )
    due_date = discord.ui.TextInput(
        label="Due date",
        placeholder="May 30, Friday, or leave blank",
        required=False,
        max_length=80,
    )
    tags = discord.ui.TextInput(
        label="Tags, comma-separated",
        placeholder="graphics, bug, renderer",
        required=False,
        max_length=200,
    )

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Tasks can only be created inside a server.", ephemeral=True)
            return

        title = str(self.task_title.value).strip()
        if not title:
            await interaction.response.send_message("Task title cannot be empty.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        forum = await get_task_forum(self.bot)
        task = create_task_record(
            guild_id=interaction.guild.id,
            forum_channel_id=forum.id,
            title=title,
            description=str(self.description.value).strip(),
            priority=str(self.priority.value).strip(),
            creator_id=interaction.user.id,
            due_date=str(self.due_date.value).strip(),
            tags=str(self.tags.value).strip(),
        )

        created = await forum.create_thread(
            name=task_thread_title(task),
            content=f"Task #{task['id']} created by {interaction.user.mention}.",
            embed=task_embed(task),
            view=TaskControls(),
            applied_tags=matching_forum_tags(forum, task),
        )

        thread = created.thread
        starter_message = created.message

        updated = update_task(
            task["id"],
            interaction.user.id,
            "discord_thread_created",
            thread_id=thread.id,
            message_id=starter_message.id,
        )

        if updated:
            await sync_discord_task(self.bot, updated)

        await interaction.followup.send(
            f"Created task #{task['id']}: {thread.mention}",
            ephemeral=True,
        )


class KanbanBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        init_db()
        self.add_view(TaskControls())  # Registers persistent buttons after bot restarts.

        self.tree.add_command(task_group)

        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Synced slash commands to guild {GUILD_ID}")
        else:
            await self.tree.sync()
            print("Synced slash commands globally. This can take a while to appear.")

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user} (ID: {self.user.id if self.user else 'unknown'})")


task_group = app_commands.Group(name="task", description="Discord-native Kanban task commands")


@task_group.command(name="create", description="Open a form to create a new task")
async def task_create(interaction: discord.Interaction) -> None:
    await interaction.response.send_modal(TaskCreateModal(interaction.client))  # type: ignore[arg-type]


@task_group.command(name="claim", description="Claim a task by ID")
async def task_claim(interaction: discord.Interaction, task_id: int) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    updated = update_task(task_id, interaction.user.id, "claimed", assignee_id=interaction.user.id)
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(f"You claimed task #{task_id}.", ephemeral=True)


@task_group.command(name="assign", description="Assign a task to a user")
async def task_assign(interaction: discord.Interaction, task_id: int, user: discord.Member) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    updated = update_task(task_id, interaction.user.id, "assigned", assignee_id=user.id)
    if updated:
        await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(f"Assigned task #{task_id} to {user.mention}.", ephemeral=True)


@task_group.command(name="move", description="Move a task to another status")
@app_commands.choices(
    status=[app_commands.Choice(name=s, value=s) for s in ["To Do", "In Progress", "Review", "Done"]]
)
async def task_move(interaction: discord.Interaction, task_id: int, status: app_commands.Choice[str]) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    updated = update_task(
        task_id,
        interaction.user.id,
        "status_changed",
        status=status.value,
        archived=0,
    )
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
        await interaction.followup.send(f"Archived task #{task_id}. It is still stored in the database.", ephemeral=True)


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


@task_group.command(name="search", description="Search tasks by status, priority, tag, or assignee")
@app_commands.choices(
    status=[app_commands.Choice(name=s, value=s) for s in STATUS_CHOICES],
    priority=[app_commands.Choice(name=p, value=p) for p in PRIORITY_CHOICES],
)
async def task_search(
    interaction: discord.Interaction,
    status: Optional[app_commands.Choice[str]] = None,
    priority: Optional[app_commands.Choice[str]] = None,
    tag: Optional[str] = None,
    assignee: Optional[discord.Member] = None,
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
        assignee_id=assignee.id if assignee else None,
        include_archived=include_archived,
        limit=10,
    )

    if not results:
        await interaction.response.send_message("No matching tasks found.", ephemeral=True)
        return

    lines = []
    for task in results:
        assignee_text = f"<@{task['assignee_id']}>" if task.get("assignee_id") else "Unassigned"
        thread_text = f"<#{task['thread_id']}>" if task.get("thread_id") else "No thread"
        archived_text = " — archived" if task.get("archived") else ""
        lines.append(
            f"**#{task['id']}** {thread_text} — **{task['status']}** — {task['priority']} — {assignee_text}{archived_text}\n"
            f"{task['title']}"
        )

    await interaction.response.send_message("\n\n".join(lines), ephemeral=True)


@task_group.command(name="info", description="Show one task by ID")
async def task_info(interaction: discord.Interaction, task_id: int) -> None:
    task = get_task(task_id)
    if not task:
        await interaction.response.send_message("Task not found.", ephemeral=True)
        return

    view = TaskControls() if not task.get("archived") else None
    await interaction.response.send_message(embed=task_embed(task), view=view, ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Missing DISCORD_TOKEN in environment or .env file.")
    if not TASK_FORUM_CHANNEL_ID:
        raise RuntimeError("Missing TASK_FORUM_CHANNEL_ID in environment or .env file.")

    bot = KanbanBot()
    bot.run(DISCORD_TOKEN)
