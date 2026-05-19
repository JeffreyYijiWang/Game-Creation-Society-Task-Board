from __future__ import annotations

import re
from datetime import date, datetime

import discord
from dateutil import parser as date_parser

from taskbot.config import settings
from taskbot.constants import DEV_ENVIRONMENTS, GAME_ENGINES, JOB_ROLES, PRIORITY_CHOICES, STATUS_CHOICES


def now_iso() -> str:
    return discord.utils.utcnow().isoformat()


def today_local() -> date:
    return datetime.now(settings.timezone).date()


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


def normalize_choice(value: str | None, choices: list[str], default: str) -> str:
    if not value:
        return default
    for choice in choices:
        if value.strip().lower() == choice.lower():
            return choice
    return default


def normalize_status(status: str | None) -> str:
    return normalize_choice(status, STATUS_CHOICES, "To Do")


def normalize_priority(priority: str | None) -> str:
    return normalize_choice(priority, PRIORITY_CHOICES, "Medium")


def normalize_job_role(job_role: str | None) -> str:
    return normalize_choice(job_role, JOB_ROLES, "Programmer")


def normalize_dev_environment(env: str | None) -> str:
    return normalize_choice(env, DEV_ENVIRONMENTS, "Windows")


def normalize_dev_environments(raw: str | list[str] | tuple[str, ...] | None) -> str:
    """Normalize one or more dev environments into a comma-separated value."""
    if raw is None:
        return "Windows"
    parts = list(raw) if isinstance(raw, (list, tuple)) else [p.strip() for p in str(raw).split(",")]
    selected: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for env in DEV_ENVIRONMENTS:
            if str(part).strip().lower() == env.lower() and env.lower() not in seen:
                seen.add(env.lower())
                selected.append(env)
    return ", ".join(selected) if selected else "Windows"


def normalize_game_engine(engine: str | None) -> str:
    return normalize_choice(engine, GAME_ENGINES, "Other")


def parse_due_date_to_iso(raw: str | None) -> str:
    if not raw or not raw.strip():
        return ""
    value = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        datetime.strptime(value, "%Y-%m-%d")
        return value
    parsed = date_parser.parse(value, fuzzy=True, default=datetime.now(settings.timezone))
    return parsed.date().isoformat()


def format_user(user_id: int | None) -> str:
    return f"<@{user_id}>" if user_id else "Unassigned"


def engine_label(task: dict) -> str:
    if task.get("game_engine") == "Other" and task.get("custom_game_engine"):
        return str(task["custom_game_engine"])
    return str(task.get("game_engine") or "Other")


def safe_int(value: int | str | None, default: int = 1) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default
