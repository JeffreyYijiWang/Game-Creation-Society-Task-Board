from __future__ import annotations

from pathlib import Path
import shutil

ROOT = Path.cwd()
BACKUP_SUFFIX = ".bak_v7_task_ui"

EMBEDS_OVERRIDE = r'''
# ---- v7 task-card override: cleaner task forum post -------------------------

def _taskbot_csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in str(value).replace("\n", ",").split(",") if x.strip()]


def _taskbot_mention(user_id: object) -> str:
    try:
        value = int(user_id)
    except Exception:
        return "Unassigned"
    return f"<@{value}>" if value else "Unassigned"


def _taskbot_claimers(task: dict) -> list[int]:
    try:
        from taskbot.db import get_claimers
        return get_claimers(int(task["id"]))
    except Exception:
        assignee = task.get("assignee_id")
        try:
            return [int(assignee)] if assignee else []
        except Exception:
            return []


def _taskbot_priority_label(priority: object) -> str:
    value = str(priority or "Medium").strip()
    icons = {"low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"}
    return f"{icons.get(value.lower(), '⚪')} {value}"


def task_embed(task: dict) -> discord.Embed:
    """Clean task card: no task id, raw task type, resources block, or claimer tag block."""
    title = str(task.get("title") or "Untitled Task")
    description = str(task.get("description") or "No description provided.")
    embed = discord.Embed(title=title, description=description[:4096], color=discord.Color.blurple())

    status = str(task.get("status") or "To Do")
    priority = _taskbot_priority_label(task.get("priority"))
    capacity = int(task.get("positions_needed") or task.get("claim_capacity") or 1)
    claimers = _taskbot_claimers(task)
    assignee_text = "\n".join(_taskbot_mention(x) for x in claimers) if claimers else "No one has claimed this yet."

    authors = []
    if task.get("creator_id"):
        authors.append(_taskbot_mention(task.get("creator_id")))
    for extra in _taskbot_csv(task.get("authors") or task.get("co_authors") or task.get("additional_authors")):
        authors.append(extra if extra.startswith("<@") else extra)
    authors_text = "\n".join(dict.fromkeys(authors)) if authors else "Unknown"

    os_value = task.get("dev_environment") or task.get("dev_environments") or "Any"
    engine = task.get("game_engine") or "Any"
    custom_engine = task.get("custom_game_engine") or ""
    if custom_engine and str(engine).lower() == "other":
        engine = custom_engine

    roles = task.get("job_role") or task.get("job_roles") or "Any"
    due = task.get("due_date") or "No due date"

    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Priority", value=priority, inline=True)
    embed.add_field(name=f"Assignees ({len(claimers)}/{capacity})", value=assignee_text, inline=True)
    embed.add_field(name="Authors", value=authors_text, inline=True)
    embed.add_field(name="Roles", value=str(roles), inline=True)
    embed.add_field(name="OS", value=str(os_value), inline=True)
    embed.add_field(name="Engine / Program", value=str(engine), inline=True)
    embed.add_field(name="Due", value=str(due), inline=True)

    if task.get("thumbnail_url"):
        embed.set_image(url=str(task["thumbnail_url"]))
    return embed
'''

FORUM_OVERRIDE = r'''
# ---- v7 forum title override: no task id, bracketed tags ---------------------

def _taskbot_title_parts(task: dict) -> list[str]:
    parts: list[str] = []
    def add(value: object, max_len: int = 18) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        for item in text.replace("\n", ",").split(","):
            item = item.strip()
            if item and item not in parts:
                parts.append(item[:max_len])
    add(task.get("priority"), 10)
    add(task.get("job_role") or task.get("job_roles"), 18)
    add(task.get("dev_environment") or task.get("dev_environments"), 12)
    add(task.get("game_engine"), 12)
    try:
        from taskbot.db import get_claimers
        capacity = int(task.get("positions_needed") or task.get("claim_capacity") or 1)
        if len(get_claimers(int(task["id"]))) >= capacity:
            add("Filled", 10)
    except Exception:
        pass
    return parts[:4]


def task_thread_title(task: dict) -> str:
    title = str(task.get("title") or "Untitled Task").strip()
    parts = _taskbot_title_parts(task)
    prefix = f"[{' | '.join(parts)}] " if parts else ""
    return (prefix + title)[:100]
'''

DB_ADDITION = r'''
# ---- v7 claim helpers --------------------------------------------------------

def get_claimers(task_id: int) -> list[int]:
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT user_id FROM task_claims WHERE task_id = ? AND status = 'active' ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
    return [int(row["user_id"]) for row in rows]


def unclaim_task(task_id: int, user_id: int):
    task = get_task(task_id)
    if not task:
        return False, "Task not found.", None
    timestamp = now_iso()
    with connect_db() as conn:
        cur = conn.execute(
            "UPDATE task_claims SET status = 'removed' WHERE task_id = ? AND user_id = ? AND status = 'active'",
            (task_id, user_id),
        )
        if cur.rowcount == 0:
            return False, "You have not claimed this task.", task
        remaining = conn.execute(
            "SELECT user_id FROM task_claims WHERE task_id = ? AND status = 'active' ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        new_assignee = int(remaining[0]["user_id"]) if remaining else None
        conn.execute("UPDATE tasks SET assignee_id = ?, updated_at = ? WHERE id = ?", (new_assignee, timestamp, task_id))
        conn.execute(
            """
            INSERT INTO task_events (task_id, actor_id, event_type, old_value, new_value, created_at)
            VALUES (?, ?, 'task_unclaimed', ?, ?, ?)
            """,
            (task_id, user_id, str(user_id), str(new_assignee or ""), timestamp),
        )
        conn.commit()
    return True, f"You unclaimed task #{task_id}.", get_task(task_id)
'''

UTILS_OVERRIDE = r'''
# ---- v7 due-date validation override ----------------------------------------

def parse_due_date_to_iso(value: str | None) -> str:
    from datetime import date, datetime
    if not value or not str(value).strip():
        return ""
    raw = str(value).strip()
    parsed = None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            break
        except ValueError:
            pass
    if parsed is None:
        raise ValueError("Due date must be YYYY-MM-DD, MM/DD/YYYY, or MM/DD/YY.")
    if parsed < date.today():
        raise ValueError("Due date cannot be in the past.")
    return parsed.isoformat()
'''

VIEWS_OVERRIDE = r'''
# ---- v7 task controls override ----------------------------------------------

class UnclaimConfirmView(discord.ui.View):
    def __init__(self, task: dict, user_id: int) -> None:
        super().__init__(timeout=120)
        self.task = task
        self.user_id = user_id

    @discord.ui.button(label="Confirm Unclaim", style=discord.ButtonStyle.danger, custom_id="taskbot:confirm_unclaim")
    async def confirm_unclaim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the person who opened this confirmation can use it.", ephemeral=True)
            return
        from taskbot.db import unclaim_task
        from taskbot.forum import sync_discord_task
        await interaction.response.defer(ephemeral=True)
        ok, message, updated = unclaim_task(int(self.task["id"]), int(interaction.user.id))
        if updated:
            await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="taskbot:cancel_unclaim")
    async def cancel_unclaim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Cancelled.", view=None)


class TaskControls(TaskControls):  # type: ignore[misc, no-redef]
    """Wrapper around existing task controls: removes Comment and adds Unclaim."""
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for child in list(self.children):
            label = str(getattr(child, "label", "") or "").lower()
            custom_id = str(getattr(child, "custom_id", "") or "").lower()
            if "comment" in label or "comment" in custom_id:
                try:
                    self.remove_item(child)
                except Exception:
                    pass
                continue
            if label in {"claim", "claim task"} or "claim" in custom_id:
                try:
                    child.label = "Claim / Unclaim"
                    child.style = discord.ButtonStyle.primary
                except Exception:
                    pass

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, custom_id="taskbot:unclaim_task", row=3)
    async def unclaim_task_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        task = await self.get_task_from_interaction(interaction)
        if not task:
            await interaction.response.send_message("Could not find this task in the database.", ephemeral=True)
            return
        try:
            from taskbot.db import get_claimers
            claimers = get_claimers(int(task["id"]))
        except Exception:
            claimers = []
        if int(interaction.user.id) not in claimers:
            await interaction.response.send_message("You have not claimed this task.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Are you sure you want to unclaim this task?",
            view=UnclaimConfirmView(task, int(interaction.user.id)),
            ephemeral=True,
        )
'''

def backup(path: Path) -> None:
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if path.exists() and not backup_path.exists():
        shutil.copy2(path, backup_path)

def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")

def write(rel: str, text: str) -> None:
    p = ROOT / rel
    backup(p)
    p.write_text(text, encoding="utf-8")
    print(f"[ok] wrote {rel}")

def append_once(rel: str, marker: str, block: str) -> None:
    text = read(rel)
    if marker in text:
        print(f"[skip] {rel} already has {marker}")
        return
    write(rel, text.rstrip() + "\n\n" + block.strip() + "\n")

def patch_constants() -> None:
    rel = "taskbot/constants.py"
    if not (ROOT / rel).exists():
        print("[skip] constants.py not found")
        return
    text = read(rel)
    if "OS_OPTIONS" not in text:
        text += "\n\n# User-facing label for development environment options.\nOS_OPTIONS = DEV_ENVIRONMENTS\n"
        write(rel, text)
    else:
        print("[skip] constants.py already has OS_OPTIONS")

def main() -> None:
    required = ["bot.py", "taskbot/embeds.py", "taskbot/forum.py", "taskbot/db.py", "taskbot/utils.py", "taskbot/views.py"]
    missing = [p for p in required if not (ROOT / p).exists()]
    if missing:
        raise SystemExit(f"Run this from the folder containing bot.py and taskbot/. Missing: {missing}")
    append_once("taskbot/embeds.py", "v7 task-card override", EMBEDS_OVERRIDE)
    append_once("taskbot/forum.py", "v7 forum title override", FORUM_OVERRIDE)
    append_once("taskbot/db.py", "def unclaim_task(", DB_ADDITION)
    append_once("taskbot/utils.py", "v7 due-date validation override", UTILS_OVERRIDE)
    append_once("taskbot/views.py", "v7 task controls override", VIEWS_OVERRIDE)
    patch_constants()
    print("\nDone.")
    print("Run:")
    print("  python -m compileall -q bot.py taskbot")
    print("  python .\\bot.py")
    print("\nExisting forum posts may need to be synced/edited before the new card layout appears.")

if __name__ == "__main__":
    main()
