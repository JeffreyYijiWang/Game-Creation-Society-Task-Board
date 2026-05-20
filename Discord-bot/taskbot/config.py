from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int = 0) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _int_set_env(name: str) -> set[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return set()
    return {int(part.strip()) for part in raw.split(",") if part.strip()}


@dataclass(frozen=True)
class Settings:
    discord_token: str = os.getenv("DISCORD_TOKEN", "")
    task_forum_channel_id: int = _int_env("TASK_FORUM_CHANNEL_ID")
    guild_id: int = _int_env("GUILD_ID")
    db_path: str = os.getenv("TASKBOT_DB", "taskbot.sqlite3")
    task_assigner_role: str = os.getenv("TASK_ASSIGNER_ROLE", "task-assigner")
    admin_role: str = os.getenv("TASK_ADMIN_ROLE", "task-admin")
    max_active_assignments: int = _int_env("MAX_ACTIVE_ASSIGNMENTS", 10)
    timezone_name: str = os.getenv("BOT_TIMEZONE", "America/Chicago")
    claim_discussion_channel_id: int = _int_env("CLAIM_DISCUSSION_CHANNEL_ID")
    info_page_channel_id: int = _int_env("INFO_PAGE_CHANNEL_ID")
    webhook_board_channel_ids: set[int] = None  # type: ignore[assignment]
    command_channel_ids: set[int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_channel_ids", _int_set_env("COMMAND_CHANNEL_IDS"))
        object.__setattr__(self, "webhook_board_channel_ids", _int_set_env("WEBHOOK_BOARD_CHANNEL_IDS"))

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


settings = Settings()
