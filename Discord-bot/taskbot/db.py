from __future__ import annotations

import sqlite3
from datetime import timedelta
from typing import Optional

from taskbot.config import settings
from taskbot.constants import ACTIVE_STATUSES
from taskbot.utils import (
    clean_csv_tags,
    normalize_dev_environments,
    normalize_game_engine,
    normalize_job_role,
    normalize_priority,
    normalize_status,
    now_iso,
    today_local,
)


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


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
                claim_thread_id INTEGER,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'To Do',
                priority TEXT NOT NULL DEFAULT 'Medium',
                assignee_id INTEGER,
                creator_id INTEGER NOT NULL,
                due_date TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                resource_links TEXT DEFAULT '',
                thumbnail_url TEXT DEFAULT '',
                positions_needed INTEGER NOT NULL DEFAULT 1,
                job_role TEXT DEFAULT '',
                dev_environment TEXT DEFAULT '',
                game_engine TEXT DEFAULT '',
                custom_game_engine TEXT DEFAULT '',
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        for column, ddl in {
            "claim_thread_id": "INTEGER",
            "resource_links": "TEXT DEFAULT ''",
            "thumbnail_url": "TEXT DEFAULT ''",
            "positions_needed": "INTEGER NOT NULL DEFAULT 1",
            "job_role": "TEXT DEFAULT ''",
            "dev_environment": "TEXT DEFAULT ''",
            "game_engine": "TEXT DEFAULT ''",
            "custom_game_engine": "TEXT DEFAULT ''",
        }.items():
            _ensure_column(conn, "tasks", column, ddl)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                UNIQUE(task_id, user_id),
                FOREIGN KEY(task_id) REFERENCES tasks(id)
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                uploader_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                url TEXT NOT NULL,
                content_type TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                UNIQUE(task_id, reminder_type)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                priority TEXT DEFAULT 'Medium',
                due_date TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                resource_links TEXT DEFAULT '',
                thumbnail_url TEXT DEFAULT '',
                positions_needed INTEGER NOT NULL DEFAULT 1,
                job_role TEXT DEFAULT 'Programmer',
                dev_environment TEXT DEFAULT 'Windows',
                game_engine TEXT DEFAULT 'Unity',
                custom_game_engine TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(guild_id, owner_id, name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_profiles (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                display_name TEXT DEFAULT '',
                bio TEXT DEFAULT '',
                skills TEXT DEFAULT '',
                portfolio_url TEXT DEFAULT '',
                availability TEXT DEFAULT '',
                preferred_roles TEXT DEFAULT '',
                dev_environments TEXT DEFAULT '',
                profile_image_url TEXT DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(guild_id, user_id)
            )
            """
        )
        conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> Optional[dict]:
    return dict(row) if row else None


def get_task(task_id: int) -> Optional[dict]:
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row_to_dict(row)


def get_task_by_thread(thread_id: int) -> Optional[dict]:
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE thread_id = ? OR claim_thread_id = ?", (thread_id, thread_id)).fetchone()
    return row_to_dict(row)


def get_task_by_message(message_id: int) -> Optional[dict]:
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE message_id = ?", (message_id,)).fetchone()
    return row_to_dict(row)


def create_task_record(
    *, guild_id: int, forum_channel_id: int, title: str, description: str, priority: str,
    creator_id: int, due_date: str, tags: str, resource_links: str, thumbnail_url: str,
    positions_needed: int, job_role: str, dev_environment: str, game_engine: str, custom_game_engine: str,
) -> dict:
    timestamp = now_iso()
    with connect_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (
                guild_id, forum_channel_id, title, description, status, priority, creator_id,
                due_date, tags, resource_links, thumbnail_url, positions_needed, job_role,
                dev_environment, game_engine, custom_game_engine, archived, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                guild_id, forum_channel_id, title, description, "To Do", normalize_priority(priority), creator_id,
                due_date, clean_csv_tags(tags), resource_links.strip(), thumbnail_url.strip(), max(1, int(positions_needed)),
                normalize_job_role(job_role), normalize_dev_environments(dev_environment), normalize_game_engine(game_engine),
                custom_game_engine.strip(), timestamp, timestamp,
            ),
        )
        task_id = int(cur.lastrowid)
        conn.execute("INSERT INTO task_events (task_id, actor_id, event_type, new_value, created_at) VALUES (?, ?, 'created', ?, ?)", (task_id, creator_id, title, timestamp))
        conn.commit()
    task = get_task(task_id)
    assert task is not None
    return task


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
            """INSERT INTO task_events (task_id, actor_id, event_type, old_value, new_value, created_at) VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, actor_id, event_type, str({k: old_task.get(k) for k in fields.keys()}), str(fields), now_iso()),
        )
        conn.commit()
    return get_task(task_id)


def add_event(task_id: int, actor_id: int, event_type: str, new_value: str) -> None:
    with connect_db() as conn:
        conn.execute("INSERT INTO task_events (task_id, actor_id, event_type, new_value, created_at) VALUES (?, ?, ?, ?, ?)", (task_id, actor_id, event_type, new_value, now_iso()))
        conn.commit()


def add_attachment(*, task_id: int, uploader_id: int, filename: str, url: str, content_type: str, notes: str) -> None:
    with connect_db() as conn:
        conn.execute("INSERT INTO task_attachments (task_id, uploader_id, filename, url, content_type, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (task_id, uploader_id, filename, url, content_type or "", notes or "", now_iso()))
        conn.commit()


def get_attachments(task_id: int, limit: int = 5) -> list[dict]:
    with connect_db() as conn:
        rows = conn.execute("SELECT * FROM task_attachments WHERE task_id = ? ORDER BY created_at DESC LIMIT ?", (task_id, limit)).fetchall()
    return [dict(row) for row in rows]


def get_claimers(task_id: int) -> list[int]:
    with connect_db() as conn:
        rows = conn.execute("SELECT user_id FROM task_claims WHERE task_id = ? AND status = 'active' ORDER BY created_at ASC", (task_id,)).fetchall()
    return [int(row["user_id"]) for row in rows]


def count_task_claimers(task_id: int) -> int:
    return len(get_claimers(task_id))


def count_active_assignments(user_id: int, guild_id: int) -> int:
    placeholders = ", ".join("?" for _ in ACTIVE_STATUSES)
    with connect_db() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS count FROM task_claims c JOIN tasks t ON t.id = c.task_id
            WHERE t.guild_id = ? AND c.user_id = ? AND c.status = 'active'
              AND t.archived = 0 AND t.status IN ({placeholders})
            """,
            [guild_id, user_id, *ACTIVE_STATUSES],
        ).fetchone()
    return int(row["count"])


def claim_task(task_id: int, user_id: int) -> tuple[bool, str, Optional[dict]]:
    task = get_task(task_id)
    if not task:
        return False, "Task not found.", None
    if task.get("archived"):
        return False, "This task is archived.", task
    current_claimers = get_claimers(task_id)
    if user_id in current_claimers:
        return False, "You already claimed this task.", task
    needed = max(1, int(task.get("positions_needed") or 1))
    if len(current_claimers) >= needed:
        return False, "This task already has enough people.", task
    with connect_db() as conn:
        conn.execute("INSERT OR IGNORE INTO task_claims (task_id, user_id, status, created_at) VALUES (?, ?, 'active', ?)", (task_id, user_id, now_iso()))
        if not task.get("assignee_id"):
            conn.execute("UPDATE tasks SET assignee_id = ?, updated_at = ? WHERE id = ?", (user_id, now_iso(), task_id))
        conn.execute("INSERT INTO task_events (task_id, actor_id, event_type, new_value, created_at) VALUES (?, ?, 'claimed', ?, ?)", (task_id, user_id, str(user_id), now_iso()))
        conn.commit()
    return True, "Claimed.", get_task(task_id)


def search_tasks(
    *, guild_id: int, status: str | None = None, priority: str | None = None, tag: str | None = None,
    claimer_id: int | None = None, creator_id: int | None = None, job_role: str | None = None,
    dev_environment: str | None = None, game_engine: str | None = None, include_archived: bool = False, limit: int = 10,
) -> list[dict]:
    where = ["t.guild_id = ?"]
    params: list[object] = [guild_id]
    if not include_archived:
        where.append("t.archived = 0")
    if status:
        where.append("LOWER(t.status) = LOWER(?)")
        params.append(normalize_status(status))
    if priority:
        where.append("LOWER(t.priority) = LOWER(?)")
        params.append(normalize_priority(priority))
    if tag:
        where.append("LOWER(t.tags) LIKE LOWER(?)")
        params.append(f"%{tag.strip()}%")
    if creator_id:
        where.append("t.creator_id = ?")
        params.append(creator_id)
    if claimer_id:
        where.append("EXISTS (SELECT 1 FROM task_claims c WHERE c.task_id = t.id AND c.user_id = ? AND c.status = 'active')")
        params.append(claimer_id)
    if job_role:
        where.append("LOWER(t.job_role) = LOWER(?)")
        params.append(normalize_job_role(job_role))
    if dev_environment:
        where.append("LOWER(t.dev_environment) LIKE LOWER(?)")
        params.append(f"%{dev_environment.strip()}%")
    if game_engine:
        where.append("LOWER(t.game_engine) = LOWER(?)")
        params.append(normalize_game_engine(game_engine))
    params.append(limit)
    query = f"SELECT t.* FROM tasks t WHERE {' AND '.join(where)} ORDER BY t.archived ASC, t.updated_at DESC LIMIT ?"
    with connect_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_profile_stats(user_id: int, guild_id: int) -> dict:
    with connect_db() as conn:
        active_claimed = conn.execute(
            """SELECT COUNT(*) AS count FROM task_claims c JOIN tasks t ON t.id = c.task_id WHERE t.guild_id = ? AND c.user_id = ? AND c.status = 'active' AND t.archived = 0 AND t.status IN ('To Do', 'In Progress', 'Review')""",
            (guild_id, user_id),
        ).fetchone()["count"]
        completed = conn.execute("SELECT COUNT(*) AS count FROM task_claims c JOIN tasks t ON t.id = c.task_id WHERE t.guild_id = ? AND c.user_id = ? AND t.status = 'Done'", (guild_id, user_id)).fetchone()["count"]
        created_active = conn.execute("SELECT COUNT(*) AS count FROM tasks WHERE guild_id = ? AND creator_id = ? AND archived = 0", (guild_id, user_id)).fetchone()["count"]
        created_archived = conn.execute("SELECT COUNT(*) AS count FROM tasks WHERE guild_id = ? AND creator_id = ? AND archived = 1", (guild_id, user_id)).fetchone()["count"]
    return {"active_claimed": int(active_claimed), "completed": int(completed), "created_active": int(created_active), "created_archived": int(created_archived)}


def list_user_projects(user_id: int, guild_id: int, limit: int = 10) -> list[dict]:
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT t.* FROM tasks t
            JOIN task_claims c ON c.task_id = t.id
            WHERE t.guild_id = ? AND c.user_id = ?
            ORDER BY CASE WHEN t.status = 'Done' THEN 0 ELSE 1 END, t.updated_at DESC
            LIMIT ?
            """,
            (guild_id, user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def upsert_profile(*, guild_id: int, user_id: int, display_name: str, bio: str, skills: str, portfolio_url: str, availability: str, preferred_roles: str, dev_environments: str, profile_image_url: str) -> dict:
    timestamp = now_iso()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO task_profiles (guild_id, user_id, display_name, bio, skills, portfolio_url, availability, preferred_roles, dev_environments, profile_image_url, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                display_name=excluded.display_name, bio=excluded.bio, skills=excluded.skills, portfolio_url=excluded.portfolio_url,
                availability=excluded.availability, preferred_roles=excluded.preferred_roles, dev_environments=excluded.dev_environments,
                profile_image_url=excluded.profile_image_url, updated_at=excluded.updated_at
            """,
            (guild_id, user_id, display_name.strip(), bio.strip(), clean_csv_tags(skills), portfolio_url.strip(), availability.strip(), clean_csv_tags(preferred_roles), normalize_dev_environments(dev_environments), profile_image_url.strip(), timestamp),
        )
        conn.commit()
    profile = get_profile(guild_id, user_id)
    assert profile is not None
    return profile


def get_profile(guild_id: int, user_id: int) -> Optional[dict]:
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM task_profiles WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)).fetchone()
    return row_to_dict(row)


def tasks_due_tomorrow() -> list[dict]:
    target = (today_local() + timedelta(days=1)).isoformat()
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks WHERE due_date = ? AND archived = 0 AND status NOT IN ('Done', 'Archived')
              AND id NOT IN (SELECT task_id FROM task_reminders WHERE reminder_type = 'due_day_before')
            """,
            (target,),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_reminder_sent(task_id: int, reminder_type: str) -> None:
    with connect_db() as conn:
        conn.execute("INSERT OR IGNORE INTO task_reminders (task_id, reminder_type, sent_at) VALUES (?, ?, ?)", (task_id, reminder_type, now_iso()))
        conn.commit()


def upsert_template(
    *, guild_id: int, owner_id: int, name: str, title: str, description: str, priority: str, due_date: str,
    tags: str, resource_links: str, thumbnail_url: str, positions_needed: int, job_role: str,
    dev_environment: str, game_engine: str, custom_game_engine: str,
) -> dict:
    timestamp = now_iso()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO task_templates (guild_id, owner_id, name, title, description, priority, due_date, tags, resource_links, thumbnail_url, positions_needed, job_role, dev_environment, game_engine, custom_game_engine, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, owner_id, name) DO UPDATE SET
                title=excluded.title, description=excluded.description, priority=excluded.priority, due_date=excluded.due_date,
                tags=excluded.tags, resource_links=excluded.resource_links, thumbnail_url=excluded.thumbnail_url,
                positions_needed=excluded.positions_needed, job_role=excluded.job_role, dev_environment=excluded.dev_environment,
                game_engine=excluded.game_engine, custom_game_engine=excluded.custom_game_engine, updated_at=excluded.updated_at
            """,
            (guild_id, owner_id, name.strip(), title.strip(), description.strip(), normalize_priority(priority), due_date, clean_csv_tags(tags), resource_links.strip(), thumbnail_url.strip(), max(1, int(positions_needed)), normalize_job_role(job_role), normalize_dev_environments(dev_environment), normalize_game_engine(game_engine), custom_game_engine.strip(), timestamp, timestamp),
        )
        conn.commit()
    template = get_template(guild_id, owner_id, name)
    assert template is not None
    return template


def get_template(guild_id: int, owner_id: int, name: str) -> Optional[dict]:
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM task_templates WHERE guild_id = ? AND owner_id = ? AND LOWER(name) = LOWER(?)", (guild_id, owner_id, name.strip())).fetchone()
    return row_to_dict(row)


def list_templates(guild_id: int, owner_id: int) -> list[dict]:
    with connect_db() as conn:
        rows = conn.execute("SELECT * FROM task_templates WHERE guild_id = ? AND owner_id = ? ORDER BY updated_at DESC", (guild_id, owner_id)).fetchall()
    return [dict(row) for row in rows]


def delete_template(guild_id: int, owner_id: int, name: str) -> bool:
    with connect_db() as conn:
        cur = conn.execute("DELETE FROM task_templates WHERE guild_id = ? AND owner_id = ? AND LOWER(name) = LOWER(?)", (guild_id, owner_id, name.strip()))
        conn.commit()
    return cur.rowcount > 0
