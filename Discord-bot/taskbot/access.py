from __future__ import annotations

import discord

from taskbot.config import settings


def has_role(member: discord.Member, role_name: str) -> bool:
    return any(role.name == role_name for role in member.roles)


def is_admin_member(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
        or has_role(member, settings.admin_role)
    )


def is_task_assigner(member: discord.Member) -> bool:
    return has_role(member, settings.task_assigner_role) or is_admin_member(member)


def can_manage_task(member: discord.Member, task: dict) -> bool:
    if is_admin_member(member):
        return True
    if not is_task_assigner(member):
        return False
    return int(task.get("creator_id") or 0) == member.id
