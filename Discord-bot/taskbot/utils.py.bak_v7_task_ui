from __future__ import annotations

import re
from datetime import date, datetime

import discord
from dateutil import parser as date_parser

from taskbot.config import settings
from taskbot.constants import DEV_ENVIRONMENTS, GAME_ENGINES, GAME_PROGRAMS, JOB_ROLES, PRIORITY_CHOICES, STATUS_CHOICES, TASK_TYPES


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


def normalize_job_roles(raw: str | list[str] | tuple[str, ...] | None) -> str:
    """Normalize one or more job roles into a comma-separated value."""
    if raw is None:
        return "Programmer"
    parts = list(raw) if isinstance(raw, (list, tuple)) else [p.strip() for p in str(raw).split(",")]
    selected: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for role in JOB_ROLES:
            if str(part).strip().lower() == role.lower() and role.lower() not in seen:
                seen.add(role.lower())
                selected.append(role)
    return ", ".join(selected) if selected else "Programmer"


def normalize_dev_environment(env: str | None) -> str:
    return normalize_choice(env, DEV_ENVIRONMENTS, "Windows")


def normalize_dev_environments(envs: str | list[str] | None) -> str:
    if not envs:
        return "Windows"
    if isinstance(envs, str):
        raw_parts = [part.strip() for part in envs.split(",") if part.strip()]
    else:
        raw_parts = [str(part).strip() for part in envs if str(part).strip()]

    valid: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        match = normalize_choice(part, DEV_ENVIRONMENTS, "")
        if match and match not in seen:
            seen.add(match)
            valid.append(match)
    return ", ".join(valid) if valid else "Windows"


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


def normalize_task_type(task_type: str | None) -> str:
    return normalize_choice(task_type, TASK_TYPES, "Feature")


def normalize_task_types(raw: str | list[str] | tuple[str, ...] | None) -> str:
    """Normalize one or more task-type dividers into a comma-separated value."""
    if raw is None:
        return "Feature"
    parts = list(raw) if isinstance(raw, (list, tuple)) else [p.strip() for p in str(raw).split(",")]
    selected: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for task_type in TASK_TYPES:
            if str(part).strip().lower() == task_type.lower() and task_type.lower() not in seen:
                seen.add(task_type.lower())
                selected.append(task_type)
    return ", ".join(selected) if selected else "Feature"


def split_filter_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in str(raw).replace(";", ",").split(",") if part.strip()]


def normalize_game_programs(raw: str | list[str] | tuple[str, ...] | None) -> str:
    """Normalize one or more software/program familiarity tags."""
    if raw is None:
        return ""
    parts = list(raw) if isinstance(raw, (list, tuple)) else [p.strip() for p in str(raw).split(",")]
    selected: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for program in GAME_PROGRAMS:
            if str(part).strip().lower() == program.lower() and program.lower() not in seen:
                seen.add(program.lower())
                selected.append(program)
    # Keep custom entries too, because tool familiarity can be wider than the preset list.
    for part in parts:
        cleaned = str(part).strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            selected.append(cleaned)
    return ", ".join(selected)


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
