from __future__ import annotations

from enum import IntEnum
from typing import Any, Iterable, Sequence

import discord


IS_COMPONENTS_V2 = 1 << 15


class ComponentType(IntEnum):
    ACTION_ROW = 1
    BUTTON = 2
    STRING_SELECT = 3
    TEXT_INPUT = 4
    USER_SELECT = 5
    ROLE_SELECT = 6 
    MENTIONABLE_SELECT = 7
    CHANNEL_SELECT = 8
    SECTION = 9
    TEXT_DISPLAY = 10
    THUMBNAIL = 11
    MEDIA_GALLERY = 12
    FILE = 13
    SEPARATOR = 14
    CONTAINER = 17
    LABEL = 18
    FILE_UPLOAD = 19
    RADIO_GROUP = 21
    CHECKBOX_GROUP = 22
    CHECKBOX = 23


class ButtonStyle(IntEnum):
    PRIMARY = 1
    SECONDARY = 2
    SUCCESS = 3
    DANGER = 4
    LINK = 5
    PREMIUM = 6


class TextInputStyle(IntEnum):
    SHORT = 1
    PARAGRAPH = 2


def _check_len(name: str, value: str | None, *, min_len: int = 0, max_len: int) -> None:
    if value is None:
        return
    if len(value) < min_len or len(value) > max_len:
        raise ValueError(f"{name} must be {min_len}-{max_len} characters; got {len(value)}")


def _clean_str(value: object, default: str = "") -> str:
    return str(value if value is not None else default).strip()


def _clip(value: object, limit: int) -> str:
    text = _clean_str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_clean_str(x) for x in value if _clean_str(x)]
    return [x.strip() for x in str(value).replace("\n", ",").split(",") if x.strip()]


def _mention(user_id: object) -> str:
    try:
        value = int(user_id)
    except Exception:
        return "Unassigned"
    return f"<@{value}>" if value else "Unassigned"


def _emoji_obj(emoji: str | dict | None) -> dict[str, Any] | None:
    if not emoji:
        return None
    if isinstance(emoji, dict):
        return emoji
    return {"name": str(emoji)}


# ---------------------------------------------------------------------------
# Raw JSON component builders.
# These mirror Discord's v2 component payloads and are useful for webhooks,
# testing, or future discord.py features that are not wrapped yet.
# ---------------------------------------------------------------------------

def v2_message_payload(components: Sequence[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    if len(components) > 40:
        raise ValueError("Components V2 messages allow up to 40 total components.")
    return {"flags": IS_COMPONENTS_V2, "components": list(components), **extra}


def select_option(
    label: str,
    value: str,
    *,
    description: str | None = None,
    emoji: str | dict | None = None,
    default: bool = False,
) -> dict[str, Any]:
    _check_len("select option label", label, min_len=1, max_len=100)
    _check_len("select option value", value, min_len=1, max_len=100)
    _check_len("select option description", description, max_len=100)
    out: dict[str, Any] = {"label": label, "value": value}
    if description:
        out["description"] = description
    em = _emoji_obj(emoji)
    if em:
        out["emoji"] = em
    if default:
        out["default"] = True
    return out


def button(
    *,
    label: str | None = None,
    custom_id: str | None = None,
    style: int | ButtonStyle = ButtonStyle.SECONDARY,
    emoji: str | dict | None = None,
    url: str | None = None,
    sku_id: int | str | None = None,
    disabled: bool = False,
    id: int | None = None,
) -> dict[str, Any]:
    style_i = int(style)
    _check_len("button label", label, max_len=80)
    _check_len("button custom_id", custom_id, min_len=1, max_len=100)
    _check_len("button url", url, max_len=512)

    out: dict[str, Any] = {"type": int(ComponentType.BUTTON), "style": style_i}
    if id is not None:
        out["id"] = id
    if disabled:
        out["disabled"] = True

    if style_i == ButtonStyle.LINK:
        if not url:
            raise ValueError("Link buttons require url.")
        out["url"] = url
        if label:
            out["label"] = label
    elif style_i == ButtonStyle.PREMIUM:
        if not sku_id:
            raise ValueError("Premium buttons require sku_id.")
        out["sku_id"] = str(sku_id)
    else:
        if not custom_id:
            raise ValueError("Non-link/non-premium buttons require custom_id.")
        out["custom_id"] = custom_id
        if label:
            out["label"] = label

    em = _emoji_obj(emoji)
    if em and style_i != ButtonStyle.PREMIUM:
        out["emoji"] = em

    return out


def string_select(
    *,
    custom_id: str,
    options: Sequence[dict[str, Any]],
    placeholder: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    required: bool | None = None,
    disabled: bool | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    _check_len("string select custom_id", custom_id, min_len=1, max_len=100)
    _check_len("string select placeholder", placeholder, max_len=150)
    if not 1 <= len(options) <= 25:
        raise ValueError("String select requires 1-25 options.")
    if not 0 <= min_values <= 25 or not 1 <= max_values <= 25 or min_values > max_values:
        raise ValueError("Invalid min_values/max_values for string select.")

    out: dict[str, Any] = {
        "type": int(ComponentType.STRING_SELECT),
        "custom_id": custom_id,
        "options": list(options),
        "min_values": min_values,
        "max_values": max_values,
    }
    if id is not None:
        out["id"] = id
    if placeholder:
        out["placeholder"] = placeholder
    if required is not None:
        out["required"] = required
    if disabled is not None:
        out["disabled"] = disabled
    return out


def entity_select(
    component_type: ComponentType,
    *,
    custom_id: str,
    placeholder: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    required: bool | None = None,
    disabled: bool | None = None,
    default_values: Sequence[dict[str, Any]] | None = None,
    channel_types: Sequence[int] | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    if component_type not in {
        ComponentType.USER_SELECT,
        ComponentType.ROLE_SELECT,
        ComponentType.MENTIONABLE_SELECT,
        ComponentType.CHANNEL_SELECT,
    }:
        raise ValueError("entity_select only supports user/role/mentionable/channel selects.")
    _check_len("select custom_id", custom_id, min_len=1, max_len=100)
    _check_len("select placeholder", placeholder, max_len=150)
    if not 0 <= min_values <= 25 or not 1 <= max_values <= 25 or min_values > max_values:
        raise ValueError("Invalid min_values/max_values for select.")

    out: dict[str, Any] = {
        "type": int(component_type),
        "custom_id": custom_id,
        "min_values": min_values,
        "max_values": max_values,
    }
    if id is not None:
        out["id"] = id
    if placeholder:
        out["placeholder"] = placeholder
    if default_values:
        out["default_values"] = list(default_values)
    if channel_types and component_type == ComponentType.CHANNEL_SELECT:
        out["channel_types"] = list(channel_types)
    if required is not None:
        out["required"] = required
    if disabled is not None:
        out["disabled"] = disabled
    return out


def user_select(**kwargs: Any) -> dict[str, Any]:
    return entity_select(ComponentType.USER_SELECT, **kwargs)


def role_select(**kwargs: Any) -> dict[str, Any]:
    return entity_select(ComponentType.ROLE_SELECT, **kwargs)


def mentionable_select(**kwargs: Any) -> dict[str, Any]:
    return entity_select(ComponentType.MENTIONABLE_SELECT, **kwargs)


def channel_select(**kwargs: Any) -> dict[str, Any]:
    return entity_select(ComponentType.CHANNEL_SELECT, **kwargs)


def action_row(components: Sequence[dict[str, Any]], *, id: int | None = None) -> dict[str, Any]:
    if not components:
        raise ValueError("Action row must contain components.")
    types = {c.get("type") for c in components}
    select_types = {
        int(ComponentType.STRING_SELECT),
        int(ComponentType.USER_SELECT),
        int(ComponentType.ROLE_SELECT),
        int(ComponentType.MENTIONABLE_SELECT),
        int(ComponentType.CHANNEL_SELECT),
    }
    if types == {int(ComponentType.BUTTON)}:
        if len(components) > 5:
            raise ValueError("Action row can contain at most 5 buttons.")
    elif len(components) == 1 and next(iter(types)) in select_types:
        pass
    else:
        raise ValueError("Action row can contain either up to 5 buttons or a single select.")
    out: dict[str, Any] = {"type": int(ComponentType.ACTION_ROW), "components": list(components)}
    if id is not None:
        out["id"] = id
    return out


def text_display(content: str, *, id: int | None = None) -> dict[str, Any]:
    out = {"type": int(ComponentType.TEXT_DISPLAY), "content": _clip(content, 4000)}
    if id is not None:
        out["id"] = id
    return out


def thumbnail(url: str, *, description: str | None = None, spoiler: bool = False, id: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": int(ComponentType.THUMBNAIL), "media": {"url": url}}
    if id is not None:
        out["id"] = id
    if description:
        out["description"] = description
    if spoiler:
        out["spoiler"] = True
    return out


def media_gallery_item(url: str, *, description: str | None = None, spoiler: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"media": {"url": url}}
    if description:
        out["description"] = description
    if spoiler:
        out["spoiler"] = True
    return out


def media_gallery(items: Sequence[dict[str, Any]], *, id: int | None = None) -> dict[str, Any]:
    if not 1 <= len(items) <= 10:
        raise ValueError("Media gallery requires 1-10 items.")
    out: dict[str, Any] = {"type": int(ComponentType.MEDIA_GALLERY), "items": list(items)}
    if id is not None:
        out["id"] = id
    return out


def file_component(url: str, *, spoiler: bool = False, id: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": int(ComponentType.FILE), "file": {"url": url}}
    if id is not None:
        out["id"] = id
    if spoiler:
        out["spoiler"] = True
    return out


def separator(*, spacing: int | None = None, divider: bool | None = None, id: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": int(ComponentType.SEPARATOR)}
    if id is not None:
        out["id"] = id
    if spacing is not None:
        out["spacing"] = spacing
    if divider is not None:
        out["divider"] = divider
    return out


def section(
    components: Sequence[dict[str, Any]],
    *,
    accessory: dict[str, Any],
    id: int | None = None,
) -> dict[str, Any]:
    if not 1 <= len(components) <= 3:
        raise ValueError("Section requires 1-3 child components.")
    if any(c.get("type") != int(ComponentType.TEXT_DISPLAY) for c in components):
        raise ValueError("Section child components must be Text Display components.")
    if accessory.get("type") not in {int(ComponentType.BUTTON), int(ComponentType.THUMBNAIL)}:
        raise ValueError("Section accessory must be Button or Thumbnail.")
    out: dict[str, Any] = {
        "type": int(ComponentType.SECTION),
        "components": list(components),
        "accessory": accessory,
    }
    if id is not None:
        out["id"] = id
    return out


def container(components: Sequence[dict[str, Any]], *, accent_color: int | None = None, spoiler: bool = False, id: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": int(ComponentType.CONTAINER), "components": list(components)}
    if id is not None:
        out["id"] = id
    if accent_color is not None:
        out["accent_color"] = int(accent_color)
    if spoiler:
        out["spoiler"] = True
    return out


def text_input(
    *,
    custom_id: str,
    style: int | TextInputStyle = TextInputStyle.SHORT,
    min_length: int | None = None,
    max_length: int | None = None,
    required: bool = True,
    value: str | None = None,
    placeholder: str | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    _check_len("text input custom_id", custom_id, min_len=1, max_len=100)
    _check_len("text input value", value, max_len=4000)
    _check_len("text input placeholder", placeholder, max_len=100)
    out: dict[str, Any] = {"type": int(ComponentType.TEXT_INPUT), "custom_id": custom_id, "style": int(style), "required": required}
    if id is not None:
        out["id"] = id
    if min_length is not None:
        out["min_length"] = min_length
    if max_length is not None:
        out["max_length"] = max_length
    if value is not None:
        out["value"] = value
    if placeholder:
        out["placeholder"] = placeholder
    return out


def file_upload(*, custom_id: str, min_values: int = 0, max_values: int = 10, required: bool = False, id: int | None = None) -> dict[str, Any]:
    _check_len("file upload custom_id", custom_id, min_len=1, max_len=100)
    out: dict[str, Any] = {
        "type": int(ComponentType.FILE_UPLOAD),
        "custom_id": custom_id,
        "min_values": min_values,
        "max_values": max_values,
        "required": required,
    }
    if id is not None:
        out["id"] = id
    return out


def checkbox(*, label: str, value: str, description: str | None = None, emoji: str | dict | None = None, default: bool = False) -> dict[str, Any]:
    return select_option(label, value, description=description, emoji=emoji, default=default)


def checkbox_group(
    *,
    custom_id: str,
    options: Sequence[dict[str, Any]],
    min_values: int = 0,
    max_values: int | None = None,
    required: bool = False,
    id: int | None = None,
) -> dict[str, Any]:
    _check_len("checkbox group custom_id", custom_id, min_len=1, max_len=100)
    out: dict[str, Any] = {
        "type": int(ComponentType.CHECKBOX_GROUP),
        "custom_id": custom_id,
        "options": list(options),
        "min_values": min_values,
        "max_values": max_values if max_values is not None else len(options),
        "required": required,
    }
    if id is not None:
        out["id"] = id
    return out


def radio_group(
    *,
    custom_id: str,
    options: Sequence[dict[str, Any]],
    required: bool = True,
    id: int | None = None,
) -> dict[str, Any]:
    _check_len("radio group custom_id", custom_id, min_len=1, max_len=100)
    out: dict[str, Any] = {
        "type": int(ComponentType.RADIO_GROUP),
        "custom_id": custom_id,
        "options": list(options),
        "required": required,
    }
    if id is not None:
        out["id"] = id
    return out


def label(
    *,
    label: str,
    component: dict[str, Any],
    description: str | None = None,
    id: int | None = None,
) -> dict[str, Any]:
    _check_len("modal label", label, min_len=1, max_len=45)
    _check_len("modal label description", description, max_len=100)
    out: dict[str, Any] = {"type": int(ComponentType.LABEL), "label": label, "component": component}
    if id is not None:
        out["id"] = id
    if description:
        out["description"] = description
    return out


def modal_payload(*, custom_id: str, title: str, components: Sequence[dict[str, Any]]) -> dict[str, Any]:
    _check_len("modal custom_id", custom_id, min_len=1, max_len=100)
    _check_len("modal title", title, min_len=1, max_len=45)
    return {"custom_id": custom_id, "title": title, "components": list(components)}


def validate_unique_custom_ids(components: Sequence[dict[str, Any]]) -> None:
    seen: set[str] = set()

    def walk(c: dict[str, Any]) -> None:
        cid = c.get("custom_id")
        if cid:
            if cid in seen:
                raise ValueError(f"Duplicate component custom_id: {cid}")
            seen.add(cid)
        for key in ("components", "options"):
            for child in c.get(key, []) or []:
                if isinstance(child, dict):
                    walk(child)
        for key in ("component", "accessory"):
            child = c.get(key)
            if isinstance(child, dict):
                walk(child)

    for comp in components:
        walk(comp)


# ---------------------------------------------------------------------------
# discord.py LayoutView adapter for this bot.
# ---------------------------------------------------------------------------

def supports_components_v2() -> bool:
    return all(
        hasattr(discord.ui, name)
        for name in ("LayoutView", "TextDisplay", "Container", "Section", "Separator", "ActionRow")
    )


def _new_text_display(content: str) -> Any:
    cls = getattr(discord.ui, "TextDisplay")
    try:
        return cls(content)
    except TypeError:
        return cls(content=content)


def _add(parent: Any, child: Any) -> None:
    parent.add_item(child)


def _claimers(task: dict[str, Any]) -> list[int]:
    try:
        from taskbot.db import get_claimers

        return get_claimers(int(task["id"]))
    except Exception:
        assignee = task.get("assignee_id")
        try:
            return [int(assignee)] if assignee else []
        except Exception:
            return []


def _capacity(task: dict[str, Any]) -> int:
    try:
        return max(1, int(task.get("positions_needed") or task.get("claim_capacity") or 1))
    except Exception:
        return 1


def _task_tags(task: dict[str, Any]) -> list[str]:
    out: list[str] = []

    def add(value: object, limit: int = 18) -> None:
        for part in _csv(value):
            cleaned = part.strip()
            if cleaned and cleaned not in out:
                out.append(cleaned[:limit])

    add(task.get("priority"), 10)
    add(task.get("job_role") or task.get("job_roles"), 18)
    add(task.get("dev_environment") or task.get("dev_environments"), 14)
    add(task.get("game_engine"), 14)
    add(task.get("task_types") or task.get("task_type"), 14)

    if len(_claimers(task)) >= _capacity(task):
        out.append("Filled")

    return out[:6]


def task_v2_title(task: dict[str, Any]) -> str:
    tags = _task_tags(task)
    prefix = f"[{' | '.join(tags)}] " if tags else ""
    return _clip(prefix + _clean_str(task.get("title"), "Untitled Task"), 100)


def _priority(task: dict[str, Any]) -> str:
    raw = _clean_str(task.get("priority"), "Medium")
    icons = {"low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"}
    return f"{icons.get(raw.lower(), '⚪')} {raw}"


def _authors(task: dict[str, Any]) -> str:
    authors: list[str] = []
    if task.get("creator_id"):
        authors.append(_mention(task.get("creator_id")))
    for item in _csv(task.get("authors") or task.get("co_authors") or task.get("additional_authors")):
        authors.append(item if item.startswith("<@") else item)
    deduped = list(dict.fromkeys(authors))
    return "\n".join(deduped) if deduped else "Unknown"


def _engine(task: dict[str, Any]) -> str:
    engine = _clean_str(task.get("game_engine"), "Any")
    custom = _clean_str(task.get("custom_game_engine"))
    return custom if custom and engine.lower() == "other" else engine


def _os(task: dict[str, Any]) -> str:
    return _clean_str(task.get("dev_environment") or task.get("dev_environments"), "Any")


def task_card_markdown(task: dict[str, Any]) -> str:
    title = _clean_str(task.get("title"), "Untitled Task")
    description = _clean_str(task.get("description"), "No description provided.")
    tags = _task_tags(task)
    tag_line = " ".join(f"`{tag}`" for tag in tags) if tags else "`General`"
    claimers = _claimers(task)
    cap = _capacity(task)
    assignee_body = "\n".join(_mention(x) for x in claimers) if claimers else "No one has claimed this yet."

    return _clip(
        "\n".join(
            [
                f"# {title}",
                tag_line,
                "",
                _clip(description, 1800),
                "",
                f"**Status:** {task.get('status') or 'To Do'}",
                f"**Priority:** {_priority(task)}",
                f"**Assignees ({len(claimers)}/{cap}):**\n{assignee_body}",
                f"**Authors:**\n{_authors(task)}",
                f"**Roles:** {task.get('job_role') or task.get('job_roles') or 'Any'}",
                f"**OS:** {_os(task)}",
                f"**Engine / Program:** {_engine(task)}",
                f"**Due:** {task.get('due_date') or 'No due date'}",
            ]
        ),
        4000,
    )


def embed_to_v2_markdown(embed: discord.Embed, *, fallback_title: str = "Message") -> str:
    parts: list[str] = []
    parts.append(f"# {embed.title or fallback_title}")
    if embed.description:
        parts.append(str(embed.description))
    for field in embed.fields:
        name = _clean_str(field.name)
        value = _clean_str(field.value)
        if name or value:
            parts.append(f"**{name}**\n{value}")
    if embed.footer and embed.footer.text:
        parts.append(f"-# {embed.footer.text}")
    return _clip("\n\n".join(parts), 4000)


def content_to_v2_markdown(content: str | None, *, title: str = "Message") -> str:
    if not content:
        return f"# {title}"
    if content.lstrip().startswith("#"):
        return _clip(content, 4000)
    return _clip(f"# {title}\n{content}", 4000)


class LegacyTaskButton(discord.ui.Button):
    def __init__(self, *, label: str, style: discord.ButtonStyle, candidates: Iterable[str], custom_id: str, emoji: str | None = None):
        super().__init__(label=label, style=style, custom_id=custom_id, emoji=emoji)
        self.candidates = {c.lower() for c in candidates}

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            from taskbot.views import TaskControls

            legacy = TaskControls()
            for child in legacy.children:
                label = _clean_str(getattr(child, "label", "")).lower()
                custom_id = _clean_str(getattr(child, "custom_id", "")).lower()
                if label in self.candidates or custom_id in self.candidates:
                    await child.callback(interaction)
                    return
        except Exception as exc:
            import traceback

            traceback.print_exception(type(exc), exc, exc.__traceback__)

        if not interaction.response.is_done():
            await interaction.response.send_message(
                "This v2 button could not find the matching task action. Check the bot terminal.",
                ephemeral=True,
            )


_BaseLayoutView = discord.ui.LayoutView if supports_components_v2() else discord.ui.View


class TaskV2View(_BaseLayoutView):  # type: ignore[misc]
    def __init__(self, task: dict[str, Any], *, include_controls: bool = True) -> None:
        super().__init__(timeout=None)
        if not supports_components_v2():
            return

        container_cls = getattr(discord.ui, "Container")
        separator_cls = getattr(discord.ui, "Separator")
        section_cls = getattr(discord.ui, "Section")
        action_row_cls = getattr(discord.ui, "ActionRow")

        c = container_cls()
        thumb = _v12_safe_url(task.get("thumbnail_url"))

        if thumb and hasattr(discord.ui, "Thumbnail"):
            try:
                section = section_cls(_new_text_display(task_card_markdown(task)), accessory=getattr(discord.ui, "Thumbnail")(thumb))
                _add(c, section)
            except Exception:
                _add(c, _new_text_display(task_card_markdown(task)))
        else:
            _add(c, _new_text_display(task_card_markdown(task)))

        gallery_urls = [u for u in (_v12_safe_url(x) for x in _csv(task.get("gallery_urls") or task.get("image_urls") or task.get("attachment_urls"))) if u]
        if gallery_urls and hasattr(discord.ui, "MediaGallery"):
            try:
                gallery = getattr(discord.ui, "MediaGallery")()
                for url in gallery_urls[:10]:
                    try:
                        gallery.add_item(url)
                    except Exception:
                        pass
                _add(c, separator_cls(visible=True))
                _add(c, gallery)
            except Exception:
                pass

        _add(c, separator_cls(visible=True))

        if include_controls:
            row = action_row_cls()
            row.add_item(
                LegacyTaskButton(
                    label="Claim / Unclaim",
                    emoji="🙋",
                    style=discord.ButtonStyle.primary,
                    candidates={"claim", "claim task", "taskbot:claim_task", "taskbot:claim"},
                    custom_id=f"taskbot_v2:claim:{task.get('id', 0)}",
                )
            )
            row.add_item(
                LegacyTaskButton(
                    label="Edit Task",
                    emoji="✏️",
                    style=discord.ButtonStyle.secondary,
                    candidates={"edit task", "taskbot:edit_task"},
                    custom_id=f"taskbot_v2:edit:{task.get('id', 0)}",
                )
            )
            row.add_item(
                LegacyTaskButton(
                    label="Remove Claimer",
                    emoji="➖",
                    style=discord.ButtonStyle.danger,
                    candidates={"remove claimer", "taskbot:remove_claimer"},
                    custom_id=f"taskbot_v2:remove_claimer:{task.get('id', 0)}",
                )
            )
            row.add_item(
                LegacyTaskButton(
                    label="Archive",
                    emoji="🗄️",
                    style=discord.ButtonStyle.secondary,
                    candidates={"archive", "taskbot:archive_task", "taskbot:archive"},
                    custom_id=f"taskbot_v2:archive:{task.get('id', 0)}",
                )
            )
            _add(c, row)

        self.add_item(c)


class GenericV2View(_BaseLayoutView):  # type: ignore[misc]
    def __init__(
        self,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
        title: str = "Message",
        include_separator: bool = True,
    ) -> None:
        super().__init__(timeout=None)
        if not supports_components_v2():
            return

        c = getattr(discord.ui, "Container")()
        markdown = embed_to_v2_markdown(embed, fallback_title=title) if embed else content_to_v2_markdown(content, title=title)
        _add(c, _new_text_display(markdown))

        if embed and embed.image and embed.image.url and hasattr(discord.ui, "MediaGallery"):
            try:
                gallery = getattr(discord.ui, "MediaGallery")()
                gallery.add_item(embed.image.url)
                _add(c, getattr(discord.ui, "Separator")(visible=True))
                _add(c, gallery)
            except Exception:
                pass

        if include_separator:
            _add(c, getattr(discord.ui, "Separator")(visible=True))

        self.add_item(c)


def task_message_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:
    if supports_components_v2():
        return {"view": TaskV2View(task, include_controls=include_controls)}

    from taskbot.embeds import task_embed
    from taskbot.views import TaskControls

    return {"embed": task_embed(task), "view": TaskControls() if include_controls else None}


def task_edit_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:
    if supports_components_v2():
        return {
            "content": None,
            "embeds": [],
            "attachments": [],
            "view": TaskV2View(task, include_controls=include_controls),
        }

    from taskbot.embeds import task_embed
    from taskbot.views import TaskControls

    return {"embed": task_embed(task), "view": TaskControls() if include_controls else None}


def generic_message_kwargs(*, content: str | None = None, embed: discord.Embed | None = None, title: str = "Message") -> dict[str, Any]:
    if supports_components_v2():
        return {"view": GenericV2View(content=content, embed=embed, title=title)}
    if embed is not None:
        return {"embed": embed}
    return {"content": content or ""}


def generic_edit_kwargs(*, content: str | None = None, embed: discord.Embed | None = None, title: str = "Message") -> dict[str, Any]:
    if supports_components_v2():
        return {
            "content": None,
            "embeds": [],
            "attachments": [],
            "view": GenericV2View(content=content, embed=embed, title=title),
        }
    if embed is not None:
        return {"embed": embed}
    return {"content": content or ""}


def old_task_layout_to_v2_kwargs(task: dict[str, Any], *, editing: bool = False, include_controls: bool = True) -> dict[str, Any]:
    return task_edit_kwargs(task, include_controls=include_controls) if editing else task_message_kwargs(task, include_controls=include_controls)


class _DemoButton(discord.ui.Button):
    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Button interaction received.", ephemeral=True)


class _DemoStringSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="String Select: choose one or more roles",
            min_values=1,
            max_values=3,
            options=[
                discord.SelectOption(label="Programmer", value="programmer", emoji="💻"),
                discord.SelectOption(label="2D Artist", value="2d_artist", emoji="🎨"),
                discord.SelectOption(label="Writer", value="writer", emoji="✍️"),
                discord.SelectOption(label="Playtester", value="playtester", emoji="🧪"),
            ],
            custom_id="taskbot_v2_demo:string_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Selected: {', '.join(self.values)}", ephemeral=True)


class V2DemoView(_BaseLayoutView):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__(timeout=600)
        if not supports_components_v2():
            return

        c = getattr(discord.ui, "Container")()
        _add(c, _new_text_display("# Discord Components V2 Demo\nThis verifies Text Display, Container, Section, Thumbnail, Separator, Action Row, Buttons, and Select Menus."))

        if hasattr(discord.ui, "Thumbnail"):
            try:
                section = getattr(discord.ui, "Section")(
                    _new_text_display("## Section + Thumbnail\nA section can place text beside an accessory component."),
                    accessory=getattr(discord.ui, "Thumbnail")("https://cdn.discordapp.com/embed/avatars/0.png"),
                )
                _add(c, section)
            except Exception:
                pass

        _add(c, getattr(discord.ui, "Separator")(visible=True))

        button_row = getattr(discord.ui, "ActionRow")()
        button_row.add_item(_DemoButton(label="Primary", style=discord.ButtonStyle.primary, custom_id="taskbot_v2_demo:primary"))
        button_row.add_item(_DemoButton(label="Success", style=discord.ButtonStyle.success, custom_id="taskbot_v2_demo:success"))
        button_row.add_item(_DemoButton(label="Danger", style=discord.ButtonStyle.danger, custom_id="taskbot_v2_demo:danger"))
        button_row.add_item(discord.ui.Button(label="Docs", style=discord.ButtonStyle.link, url="https://docs.discord.com/developers/components/reference"))
        _add(c, button_row)

        select_row = getattr(discord.ui, "ActionRow")()
        select_row.add_item(_DemoStringSelect())
        _add(c, select_row)

        for cls_name, label, custom_id in [
            ("UserSelect", "User Select", "taskbot_v2_demo:user_select"),
            ("RoleSelect", "Role Select", "taskbot_v2_demo:role_select"),
            ("MentionableSelect", "Mentionable Select", "taskbot_v2_demo:mentionable_select"),
            ("ChannelSelect", "Channel Select", "taskbot_v2_demo:channel_select"),
        ]:
            if hasattr(discord.ui, cls_name):
                try:
                    row = getattr(discord.ui, "ActionRow")()
                    select_cls = getattr(discord.ui, cls_name)
                    row.add_item(select_cls(placeholder=label, min_values=0, max_values=3, custom_id=custom_id))
                    _add(c, row)
                except Exception:
                    pass

        self.add_item(c)


def v2_demo_kwargs() -> dict[str, Any]:
    if supports_components_v2():
        return {"view": V2DemoView()}
    return {
        "content": "Your installed discord.py does not expose LayoutView/TextDisplay/Container. Run: python -m pip install -U discord.py"
    }


def example_raw_v2_modal_payload() -> dict[str, Any]:
    return modal_payload(
        custom_id="taskbot_v2:raw_modal_example",
        title="Task Preferences",
        components=[
            label(
                label="Task title",
                description="Short readable title.",
                component=text_input(custom_id="title", style=TextInputStyle.SHORT, max_length=100, required=True),
            ),
            label(
                label="Job roles",
                description="Pick one or more roles.",
                component=string_select(
                    custom_id="job_roles",
                    min_values=1,
                    max_values=3,
                    options=[
                        select_option("Programmer", "programmer", emoji="💻"),
                        select_option("2D Artist", "2d_artist", emoji="🎨"),
                        select_option("Writer", "writer", emoji="✍️"),
                    ],
                ),
            ),
            label(
                label="Attachments",
                description="Upload references or docs.",
                component=file_upload(custom_id="attachments", min_values=0, max_values=5, required=False),
            ),
            label(
                label="Priority",
                component=radio_group(
                    custom_id="priority",
                    options=[
                        select_option("Low", "low", emoji="🟢"),
                        select_option("Medium", "medium", emoji="🟡", default=True),
                        select_option("High", "high", emoji="🔴"),
                    ],
                ),
            ),
            label(
                label="OS targets",
                description="Select all that apply.",
                component=checkbox_group(
                    custom_id="os_targets",
                    options=[
                        checkbox(label="Windows", value="windows", emoji="🪟"),
                        checkbox(label="macOS", value="macos", emoji="🍎"),
                        checkbox(label="Linux", value="linux", emoji="🐧"),
                    ],
                ),
            ),
        ],
    )

# ---- v11 task-card visual refresh override ---------------------------------

_TASKBOT_ROLE_VISUALS = {
    "Programmer": "🔵💻 Programmer",
    "2D Artist": "🟢🎨 2D Artist",
    "Writer": "🟣✍️ Writer",
    "SFX": "🔵🔊 SFX",
    "VFX": "🟢✨ VFX",
    "Music Composer": "🔵🎵 Music Composer",
    "3D Artist": "🟡🧊 3D Artist",
    "3D Modeler": "🟠🛠️ 3D Modeler",
    "Rigging": "🟤🦴 Rigging",
    "3D Animator": "🔴🎬 3D Animator",
    "2D Animator": "❤️📹 2D Animator",
    "Playtester": "🟣🎮 Playtester",
    "UI Artist": "🟢🧩 UI Artist",
}

def _v11_role_chips(value: object) -> str:
    roles = _csv(value)
    if not roles:
        return "`Any`"
    chips = []
    for role in roles:
        label = _TASKBOT_ROLE_VISUALS.get(role, f"⚪ {role}")
        chips.append(f"`{label}`")
    return " ".join(chips)

def _v11_status_line(task: dict[str, Any]) -> str:
    status = _clean_str(task.get("status"), "To Do").lower()
    mapping = {
        "to do": "🟢 To Do",
        "todo": "🟢 To Do",
        "in progress": "🟡 In Progress",
        "review": "🩷 Review",
        "done": "⚪ Done",
        "archived": "⚫ Archived",
    }
    return f"`{mapping.get(status, status.title())}`"

def _v11_priority_line(task: dict[str, Any]) -> str:
    return f"`{_priority(task)}`"

def _v11_assignee_block(task: dict[str, Any]) -> str:
    claimers = _claimers(task)
    cap = _capacity(task)
    label = f"**Assignees ({len(claimers)}/{cap})**"
    body = "\n".join(_mention(x) for x in claimers) if claimers else "No one has claimed this yet."
    return f"{label}\n{body}"

def _v11_banner_line() -> str:
    # Faux banner strip made with white-square glyphs to approximate a white
    # banner without requiring an external hosted image.
    return "⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜"

def _v11_is_archived(task: dict[str, Any]) -> bool:
    status = _clean_str(task.get("status"), "").lower()
    return status in {"archived", "archive"}

def _v11_button_style(selected: bool = False) -> discord.ButtonStyle:
    return discord.ButtonStyle.primary if selected else discord.ButtonStyle.secondary

class _V11ProxyButton(discord.ui.Button):
    def __init__(self, *, label: str, style: discord.ButtonStyle, candidates: Iterable[str], custom_id: str, disabled: bool = False):
        super().__init__(label=label, style=style, custom_id=custom_id, disabled=disabled)
        self.candidates = {c.lower() for c in candidates}

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            from taskbot.views import TaskControls

            legacy = TaskControls()
            for child in legacy.children:
                label = _clean_str(getattr(child, "label", "")).lower()
                custom_id = _clean_str(getattr(child, "custom_id", "")).lower()
                if label in self.candidates or custom_id in self.candidates:
                    await child.callback(interaction)
                    return
        except Exception as exc:
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)

        if not interaction.response.is_done():
            await interaction.response.send_message(
                "This button could not find the matching task action. Check the bot terminal.",
                ephemeral=True,
            )

class TaskV2View(_BaseLayoutView):  # type: ignore[misc, no-redef]
    def __init__(self, task: dict[str, Any], *, include_controls: bool = True) -> None:
        super().__init__(timeout=None)
        if not supports_components_v2():
            return

        container_cls = getattr(discord.ui, "Container")
        separator_cls = getattr(discord.ui, "Separator")
        c = container_cls()

        # Faux white banner strip, then divider.
        _add(c, _new_text_display(_v11_banner_line()))
        _add(c, separator_cls(visible=True))

        # Title
        _add(c, _new_text_display(f"# {_clean_str(task.get('title'), 'Untitled Task')}"))

        # Description
        description = _clean_str(task.get("description"), "No description provided.")
        _add(c, _new_text_display(description))
        _add(c, separator_cls(visible=True))

        # Top stats block
        top_stats = "\n\n".join(
            [
                "**Status**\n" + _v11_status_line(task),
                "**Priority**\n" + _v11_priority_line(task),
                _v11_assignee_block(task),
            ]
        )
        _add(c, _new_text_display(top_stats))
        _add(c, separator_cls(visible=True))

        # Meta block
        authors = _authors(task)
        roles = _v11_role_chips(task.get("job_role") or task.get("job_roles"))
        os_text = _os(task)
        meta = "\n\n".join(
            [
                f"**Authors**\n{authors}",
                f"**Roles**\n{roles}",
                f"**OS**\n{os_text}",
            ]
        )
        _add(c, _new_text_display(meta))
        _add(c, separator_cls(visible=True))

        # Engine and due date separated for more breathing room.
        _add(c, _new_text_display(f"**Engine**\n{_engine(task)}"))
        _add(c, separator_cls(visible=False))
        _add(c, _new_text_display(f"**Due Date**\n{task.get('due_date') or 'No due date'}"))
        _add(c, separator_cls(visible=True))

        if include_controls:
            claimers = _claimers(task)
            cap = _capacity(task)
            is_archived = _v11_is_archived(task)
            status = _clean_str(task.get("status"), "To Do").lower()

            # Row 1: status buttons
            status_row = getattr(discord.ui, "ActionRow")()
            statuses = [
                ("To Do", {"to do", "todo", "taskbot:todo", "taskbot:set_status:todo", "move to to do"}),
                ("In Progress", {"in progress", "taskbot:in_progress", "move to in progress"}),
                ("Review", {"review", "taskbot:review", "move to review"}),
                ("Done", {"done", "taskbot:done", "mark done"}),
            ]
            for label, candidates in statuses:
                selected = (
                    (label == "To Do" and status in {"to do", "todo"})
                    or (label == "In Progress" and status == "in progress")
                    or (label == "Review" and status == "review")
                    or (label == "Done" and status == "done")
                )
                status_row.add_item(
                    _V11ProxyButton(
                        label=label,
                        style=_v11_button_style(selected),
                        candidates=candidates,
                        custom_id=f"taskbot_v11:{label.lower().replace(' ', '_')}:{task.get('id', 0)}",
                        disabled=is_archived,
                    )
                )
            _add(c, status_row)

            # Row 2: claim/unclaim/edit/archive
            row2 = getattr(discord.ui, "ActionRow")()
            can_claim = (len(claimers) < cap) and not is_archived
            any_claimed = bool(claimers) and not is_archived

            # Discord does not support a yellow button style. We use:
            # Claim = blue when available, grey when not; Unclaim = red when active.
            row2.add_item(
                _V11ProxyButton(
                    label="Claim",
                    style=discord.ButtonStyle.primary if can_claim else discord.ButtonStyle.secondary,
                    candidates={"claim", "claim task", "taskbot:claim_task", "taskbot:claim"},
                    custom_id=f"taskbot_v11:claim:{task.get('id', 0)}",
                    disabled=not can_claim,
                )
            )
            row2.add_item(
                _V11ProxyButton(
                    label="Unclaim",
                    style=discord.ButtonStyle.danger if any_claimed else discord.ButtonStyle.secondary,
                    candidates={"unclaim", "taskbot:unclaim_task", "taskbot:confirm_unclaim"},
                    custom_id=f"taskbot_v11:unclaim:{task.get('id', 0)}",
                    disabled=not any_claimed,
                )
            )
            row2.add_item(
                _V11ProxyButton(
                    label="Edit Post",
                    style=discord.ButtonStyle.secondary,
                    candidates={"edit task", "edit post", "taskbot:edit_task"},
                    custom_id=f"taskbot_v11:edit:{task.get('id', 0)}",
                    disabled=is_archived,
                )
            )
            row2.add_item(
                _V11ProxyButton(
                    label="Unarchive" if is_archived else "Archive",
                    style=discord.ButtonStyle.secondary if is_archived else discord.ButtonStyle.secondary,
                    candidates={"archive", "unarchive", "taskbot:archive_task", "taskbot:archive"},
                    custom_id=f"taskbot_v11:archive:{task.get('id', 0)}",
                    disabled=False,
                )
            )
            _add(c, row2)

        self.add_item(c)

def task_message_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    if supports_components_v2():
        return {"view": TaskV2View(task, include_controls=include_controls)}

    from taskbot.embeds import task_embed
    from taskbot.views import TaskControls

    return {"embed": task_embed(task), "view": TaskControls() if include_controls else None}

def task_edit_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    if supports_components_v2():
        return {
            "content": None,
            "embeds": [],
            "attachments": [],
            "view": TaskV2View(task, include_controls=include_controls),
        }

    from taskbot.embeds import task_embed
    from taskbot.views import TaskControls

    return {"embed": task_embed(task), "view": TaskControls() if include_controls else None}

# ---- v12 empty TextDisplay + URL safety fix --------------------------------

def _v12_nonempty_text(value: object, default: str = "—") -> str:
    text = _clean_str(value)
    return text if text else default


def _v12_safe_url(value: object) -> str:
    text = _clean_str(value)
    if not text:
        return ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(text)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return text
    except Exception:
        pass
    return ""


# Override the earlier helper. Discord Components V2 Text Display content must
# be 1-4000 chars, so an empty description/title/etc. must become a safe dash.
def _new_text_display(content: str):  # type: ignore[no-redef]
    cls = getattr(discord.ui, "TextDisplay")
    safe_content = _clip(_v12_nonempty_text(content), 4000)
    try:
        return cls(safe_content)
    except TypeError:
        return cls(content=safe_content)


# ---- v13 task card layout refresh ------------------------------------------
# Final override for task posts.  This keeps Discord Components v2 but removes
# the old legacy-proxy button bridge, which was causing slow/expired component
# interactions such as "Unknown interaction" on Claim/Edit/Archive.

from datetime import datetime, timezone as _taskbot_v13_timezone
from urllib.parse import urlparse as _taskbot_v13_urlparse


def _v13_nonempty(value: object, fallback: str = "\u200b") -> str:
    text = str(value if value is not None else "").strip()
    return text if text else fallback


def _v13_clip(value: object, limit: int = 3900) -> str:
    text = _v13_nonempty(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _v13_is_url(value: object) -> bool:
    try:
        parsed = _taskbot_v13_urlparse(str(value).strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def _v13_add(parent: object, child: object) -> None:
    try:
        parent.add_item(child)  # type: ignore[attr-defined]
    except Exception:
        pass


def _v13_text(content: object) -> object:
    content = _v13_clip(content, 4000)
    cls = getattr(discord.ui, "TextDisplay")
    try:
        return cls(content)
    except TypeError:
        return cls(content=content)


def _v13_sep(*, visible: bool = True, spacing: int | None = None) -> object:
    cls = getattr(discord.ui, "Separator")
    try:
        if spacing is None:
            return cls(visible=visible)
        return cls(visible=visible, spacing=spacing)
    except TypeError:
        try:
            return cls()
        except TypeError:
            return cls(visible)


def _v13_action_row() -> object:
    return getattr(discord.ui, "ActionRow")()


def _v13_split_csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = ",".join(str(v) for v in value)
    else:
        raw = str(value)
    return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]


def _v13_status_code(status: object) -> str:
    s = str(status or "To Do").strip()
    sl = s.lower()
    if sl in {"to do", "todo"}:
        return "```diff\n+ To Do\n```"
    if sl == "in progress":
        return "```ini\n[In Progress]\n```"
    if sl == "review":
        return "```css\n[Review]\n```"
    if sl == "done":
        return "```json\n\"Done\"\n```"
    if sl == "archived":
        return "```diff\n- Archived\n```"
    return f"```ini\n[{s[:64]}]\n```"


def _v13_due_text(task: dict[str, Any]) -> str:
    raw = str(task.get("due_date") or "").strip()
    if not raw:
        return "No due date"
    try:
        dt = datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=_taskbot_v13_timezone.utc)
        return f"<t:{int(dt.timestamp())}:D>"
    except Exception:
        return raw


def _v13_claimers(task: dict[str, Any]) -> list[int]:
    try:
        from taskbot.db import get_claimers
        return [int(x) for x in get_claimers(int(task["id"]))]
    except Exception:
        return []


def _v13_role_mentions(task: dict[str, Any]) -> str:
    roles = _v13_split_csv(task.get("job_role") or task.get("job_roles"))
    if not roles:
        roles = ["Role"]
    try:
        from taskbot.constants import JOB_ROLE_EMOJIS, JOB_ROLE_MENTION_IDS
    except Exception:
        JOB_ROLE_EMOJIS = {}
        JOB_ROLE_MENTION_IDS = {}

    rendered: list[str] = []
    for role in roles:
        emoji = str(JOB_ROLE_EMOJIS.get(role, "") or "").strip()
        role_id = 0
        try:
            role_id = int(JOB_ROLE_MENTION_IDS.get(role, 0) or 0)
        except Exception:
            role_id = 0
        if role_id:
            rendered.append(f"{emoji} <@&{role_id}>".strip())
        else:
            rendered.append(f"{emoji} {role}".strip())
    return " ".join(rendered)


def _v13_priority_text(task: dict[str, Any]) -> str:
    p = str(task.get("priority") or "Medium").strip()
    icon = {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "urgent": "🔴",
    }.get(p.lower(), "🟡")
    return f"`{icon} {p}`"


def _v13_header_markdown(task: dict[str, Any]) -> str:
    title = str(task.get("title") or "Untitled Task").strip()
    desc = str(task.get("description") or "No description provided.").strip()
    return f"## {title}\n{desc}"


def _v13_detail_markdown(task: dict[str, Any]) -> str:
    claimers = _v13_claimers(task)
    cap = int(task.get("positions_needed") or task.get("claim_capacity") or 1)
    assignee_text = "\n".join(f"<@{uid}>" for uid in claimers) or "No one has claimed this yet."
    authors = str(task.get("author_ids") or "").strip()
    if authors:
        author_text = "\n".join(f"<@{uid.strip()}>" for uid in authors.replace("\n", ",").split(",") if uid.strip().isdigit())
    else:
        author_text = f"<@{int(task.get('creator_id') or 0)}>" if task.get("creator_id") else "Unknown"

    os_text = ", ".join(_v13_split_csv(task.get("dev_environment") or task.get("dev_environments"))) or "Not specified"
    engine = str(task.get("custom_game_engine") or task.get("game_engine") or "Not specified").strip()
    tags = _v13_split_csv(task.get("tags"))
    tag_text = " ".join(f"`{x}`" for x in tags[:10]) if tags else ""

    return (
        f"**Status**\n{_v13_status_code(task.get('status') or 'To Do')}\n"
        f"**Priority**\n{_v13_priority_text(task)}\n"
        f"**Assignees ({len(claimers)}/{cap})**\n{assignee_text}\n\n"
        f"**Authors**\n{author_text}\n\n"
        f"**Roles**\n{_v13_role_mentions(task)}\n\n"
        f"**OS**\n{os_text}\n\n"
        f"**Engine**\n{engine}\n\n"
        f"**Due Date**\n{_v13_due_text(task)}"
        + (f"\n\n**Tags**\n{tag_text}" if tag_text else "")
    )


def task_card_markdown(task: dict[str, Any]) -> str:  # type: ignore[no-redef]
    return _v13_header_markdown(task) + "\n\n" + _v13_detail_markdown(task)


class _V13TaskButton(discord.ui.Button):
    def __init__(self, *, task_id: int, action: str, label: str, style: discord.ButtonStyle, disabled: bool = False) -> None:
        super().__init__(
            label=label,
            style=style,
            custom_id=f"taskbot_v13:{action}:{task_id}",
            disabled=disabled,
        )
        self.task_id = int(task_id)
        self.action = action

    async def _get_task(self) -> dict[str, Any] | None:
        try:
            from taskbot.db import get_task
            return get_task(self.task_id)
        except Exception:
            return None

    async def _must_manage(self, interaction: discord.Interaction, task: dict[str, Any]) -> bool:
        try:
            from taskbot.access import can_manage_task
            if isinstance(interaction.user, discord.Member) and can_manage_task(interaction.user, task):
                return True
        except Exception:
            pass
        await interaction.response.send_message(
            "Only admins or the task assigner who created this task can change this.",
            ephemeral=True,
        )
        return False

    async def callback(self, interaction: discord.Interaction) -> None:
        task = await self._get_task()
        if not task:
            await interaction.response.send_message("Could not find this task in the database.", ephemeral=True)
            return

        if self.action in {"todo", "in_progress", "review", "done"}:
            if not await self._must_manage(interaction, task):
                return
            await interaction.response.defer(ephemeral=True)
            status = {
                "todo": "To Do",
                "in_progress": "In Progress",
                "review": "Review",
                "done": "Done",
            }[self.action]
            try:
                from taskbot.db import update_task
                from taskbot.forum import sync_discord_task
                updated = update_task(int(task["id"]), int(interaction.user.id), "status_changed", status=status, archived=0)
                if updated:
                    await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
                await interaction.followup.send(f"Moved task to **{status}**.", ephemeral=True)
            except Exception as exc:
                await interaction.followup.send(f"Could not update status: {exc}", ephemeral=True)
            return

        if self.action == "claim":
            if not interaction.guild:
                await interaction.response.send_message("Tasks can only be claimed inside a server.", ephemeral=True)
                return
            try:
                from taskbot.config import settings
                from taskbot.db import claim_task, count_active_assignments, get_claimers, get_profile
                if int(interaction.user.id) in [int(x) for x in get_claimers(int(task["id"]))]:
                    await interaction.response.send_message("You already claimed this task. Use **Unclaim** to remove yourself.", ephemeral=True)
                    return
                active_count = count_active_assignments(int(interaction.user.id), int(interaction.guild.id))
                if active_count >= settings.max_active_assignments:
                    await interaction.response.send_message(
                        f"You already have {active_count} active assignments. The limit is {settings.max_active_assignments}.",
                        ephemeral=True,
                    )
                    return
                if not get_profile(int(interaction.guild.id), int(interaction.user.id)):
                    from taskbot.modals import ProfileEditModal
                    await interaction.response.send_modal(ProfileEditModal(guild_id=int(interaction.guild.id), user_id=int(interaction.user.id)))
                    return
                await interaction.response.defer(ephemeral=True)
                ok, message, updated = claim_task(int(task["id"]), int(interaction.user.id))
                if updated:
                    from taskbot.forum import sync_discord_task
                    from taskbot.notifications import notify_claim
                    await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
                    await notify_claim(interaction.client, updated, interaction.user)  # type: ignore[arg-type]
                await interaction.followup.send(message if not ok else "You claimed this task.", ephemeral=True)
            except Exception as exc:
                if interaction.response.is_done():
                    await interaction.followup.send(f"Could not claim task: {exc}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"Could not claim task: {exc}", ephemeral=True)
            return

        if self.action == "unclaim":
            try:
                from taskbot.db import get_claimers
                claimers = [int(x) for x in get_claimers(int(task["id"]))]
            except Exception:
                claimers = []
            if int(interaction.user.id) not in claimers:
                await interaction.response.send_message("You have not claimed this task.", ephemeral=True)
                return
            await interaction.response.send_message(
                "Are you sure you want to unclaim this task?",
                view=_V13UnclaimConfirmView(task_id=int(task["id"]), user_id=int(interaction.user.id)),
                ephemeral=True,
            )
            return

        if self.action == "edit":
            if not await self._must_manage(interaction, task):
                return
            from taskbot.modals import TaskEditModal
            await interaction.response.send_modal(TaskEditModal(interaction.client, task))  # type: ignore[arg-type]
            return

        if self.action == "archive":
            if not await self._must_manage(interaction, task):
                return
            await interaction.response.defer(ephemeral=True)
            try:
                from taskbot.db import update_task
                from taskbot.forum import sync_discord_task
                is_archived = bool(task.get("archived"))
                if is_archived:
                    updated = update_task(int(task["id"]), int(interaction.user.id), "unarchived", status="To Do", archived=0)
                    message = "Task unarchived and moved back to **To Do**."
                else:
                    updated = update_task(int(task["id"]), int(interaction.user.id), "archived", status="Archived", archived=1)
                    message = "Task archived."
                if updated:
                    await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
                await interaction.followup.send(message, ephemeral=True)
            except Exception as exc:
                await interaction.followup.send(f"Could not archive/unarchive task: {exc}", ephemeral=True)
            return


class _V13UnclaimConfirmView(discord.ui.View):
    def __init__(self, *, task_id: int, user_id: int) -> None:
        super().__init__(timeout=60)
        self.task_id = int(task_id)
        self.user_id = int(user_id)

    @discord.ui.button(label="Yes, unclaim", style=discord.ButtonStyle.danger, custom_id="taskbot_v13:confirm_unclaim")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if int(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Only the person who opened this confirmation can use it.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            from taskbot.db import unclaim_task
            from taskbot.forum import sync_discord_task
            ok, message, updated = unclaim_task(self.task_id, self.user_id)
            if updated:
                await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
            await interaction.followup.send(message if message else "You unclaimed this task.", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"Could not unclaim task: {exc}", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="taskbot_v13:cancel_unclaim")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Cancelled.", view=None)


_BaseLayoutView = discord.ui.LayoutView if supports_components_v2() else discord.ui.View


class TaskV2View(_BaseLayoutView):  # type: ignore[misc, no-redef]
    def __init__(self, task: dict[str, Any], *, include_controls: bool = True) -> None:
        super().__init__(timeout=None)
        if not supports_components_v2():
            return

        c = getattr(discord.ui, "Container")()

        thumb = str(task.get("thumbnail_url") or "").strip()
        if thumb and _v13_is_url(thumb) and hasattr(discord.ui, "MediaGallery"):
            try:
                gallery = getattr(discord.ui, "MediaGallery")()
                gallery.add_item(thumb)
                _v13_add(c, gallery)
                _v13_add(c, _v13_sep(visible=True))
            except Exception:
                pass

        _v13_add(c, _v13_text(_v13_header_markdown(task)))
        _v13_add(c, _v13_sep(visible=True))
        _v13_add(c, _v13_text(_v13_detail_markdown(task)))

        gallery_urls = [u for u in _v13_split_csv(task.get("gallery_urls") or task.get("image_urls") or task.get("attachment_urls")) if _v13_is_url(u)]
        if gallery_urls and hasattr(discord.ui, "MediaGallery"):
            try:
                gallery = getattr(discord.ui, "MediaGallery")()
                for url in gallery_urls[:10]:
                    try:
                        gallery.add_item(url)
                    except Exception:
                        pass
                _v13_add(c, _v13_sep(visible=True))
                _v13_add(c, gallery)
            except Exception:
                pass

        if include_controls:
            _v13_add(c, _v13_sep(visible=True))
            _v13_add(c, _v13_text("-# Change status"))

            status = str(task.get("status") or "To Do").strip().lower()
            is_archived = bool(task.get("archived")) or status == "archived"

            row1 = _v13_action_row()
            for action, label in [
                ("todo", "To Do"),
                ("in_progress", "In Progress"),
                ("review", "Review"),
                ("done", "Done"),
            ]:
                selected = (
                    (action == "todo" and status in {"to do", "todo"})
                    or (action == "in_progress" and status == "in progress")
                    or (action == "review" and status == "review")
                    or (action == "done" and status == "done")
                )
                row1.add_item(
                    _V13TaskButton(
                        task_id=int(task.get("id") or 0),
                        action=action,
                        label=label,
                        style=discord.ButtonStyle.primary if selected else discord.ButtonStyle.secondary,
                        disabled=is_archived,
                    )
                )
            _v13_add(c, row1)

            _v13_add(c, _v13_text("-# Task actions"))
            claimers = _v13_claimers(task)
            cap = int(task.get("positions_needed") or task.get("claim_capacity") or 1)
            filled = len(claimers) >= cap

            row2 = _v13_action_row()
            row2.add_item(
                _V13TaskButton(
                    task_id=int(task.get("id") or 0),
                    action="claim",
                    label="Claim",
                    style=discord.ButtonStyle.primary if not filled and not is_archived else discord.ButtonStyle.secondary,
                    disabled=filled or is_archived,
                )
            )
            row2.add_item(
                _V13TaskButton(
                    task_id=int(task.get("id") or 0),
                    action="unclaim",
                    label="Unclaim",
                    style=discord.ButtonStyle.danger if claimers and not is_archived else discord.ButtonStyle.secondary,
                    disabled=not bool(claimers) or is_archived,
                )
            )
            row2.add_item(
                _V13TaskButton(
                    task_id=int(task.get("id") or 0),
                    action="edit",
                    label="Edit Post",
                    style=discord.ButtonStyle.secondary,
                    disabled=is_archived,
                )
            )
            row2.add_item(
                _V13TaskButton(
                    task_id=int(task.get("id") or 0),
                    action="archive",
                    label="Unarchive" if is_archived else "Archive",
                    style=discord.ButtonStyle.secondary,
                    disabled=False,
                )
            )
            _v13_add(c, row2)

        self.add_item(c)


def task_message_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    if supports_components_v2():
        return {"view": TaskV2View(task, include_controls=include_controls)}
    from taskbot.embeds import task_embed
    from taskbot.views import TaskControls
    return {"embed": task_embed(task), "view": TaskControls() if include_controls else None}


def task_edit_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    if supports_components_v2():
        return {
            "content": None,
            "embeds": [],
            "attachments": [],
            "view": TaskV2View(task, include_controls=include_controls),
        }
    from taskbot.embeds import task_embed
    from taskbot.views import TaskControls
    return {"embed": task_embed(task), "view": TaskControls() if include_controls else None}

# ---- v14 task card: direct V2 buttons, real banner image, role mentions ------

from pathlib import Path as _V14Path
from datetime import datetime as _V14DateTime, time as _V14Time, timezone as _V14Timezone


def _v14_safe_url(value: object) -> str:
    text = _clean_str(value)
    if not text:
        return ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(text)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return text
    except Exception:
        pass
    return ""


def _v14_default_banner_path() -> _V14Path | None:
    path = _V14Path(__file__).resolve().parent / "assets" / "banner.png"
    return path if path.exists() else None


def _v14_uses_default_banner(task: dict[str, Any]) -> bool:
    return not _v14_safe_url(task.get("banner_url") or task.get("thumbnail_url")) and _v14_default_banner_path() is not None


def _v14_banner_url(task: dict[str, Any]) -> str:
    explicit = _v14_safe_url(task.get("banner_url") or task.get("thumbnail_url"))
    if explicit:
        return explicit
    if _v14_default_banner_path() is not None:
        return "attachment://task_banner.png"
    return ""


def _v14_banner_file(task: dict[str, Any]) -> discord.File | None:
    if not _v14_uses_default_banner(task):
        return None
    path = _v14_default_banner_path()
    if path is None:
        return None
    return discord.File(str(path), filename="task_banner.png")


def _v14_status_name(task: dict[str, Any]) -> str:
    return _clean_str(task.get("status"), "To Do")


def _v14_status_markdown(task: dict[str, Any]) -> str:
    status = _v14_status_name(task)
    low = status.lower()
    if low in {"to do", "todo"}:
        return "```diff\n+ To Do\n```"
    if low == "in progress":
        return "```fix\nIn Progress\n```"
    if low == "review":
        return "```ini\n[Review]\n```"
    if low == "done":
        return "```css\n[Done]\n```"
    if low == "archived":
        return "```elm\nArchived\n```"
    return f"`{status}`"


def _v14_due_date(task: dict[str, Any]) -> str:
    raw = _clean_str(task.get("due_date"))
    if not raw:
        return "No due date"

    # Database usually stores YYYY-MM-DD. Discord timestamps give a clean date
    # plus relative countdown.
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = _V14DateTime.strptime(raw[:19], fmt)
            if fmt == "%Y-%m-%d":
                dt = _V14DateTime.combine(dt.date(), _V14Time(hour=12))
            dt = dt.replace(tzinfo=_V14Timezone.utc)
            ts = int(dt.timestamp())
            return f"<t:{ts}:D>\n<t:{ts}:R>"
        except Exception:
            pass

    return raw


def _v14_role_chips(value: object) -> str:
    roles = _csv(value)
    if not roles:
        return "`Any`"

    try:
        from taskbot.constants import JOB_ROLE_EMOJIS, JOB_ROLE_MENTION_IDS
    except Exception:
        JOB_ROLE_EMOJIS = {}
        JOB_ROLE_MENTION_IDS = {}

    chips: list[str] = []
    for role in roles:
        role = _clean_str(role)
        if not role:
            continue
        emoji = JOB_ROLE_EMOJIS.get(role, "")
        role_id = JOB_ROLE_MENTION_IDS.get(role)
        try:
            role_id_int = int(role_id)
        except Exception:
            role_id_int = 0

        if role_id_int:
            chips.append(f"{emoji} <@&{role_id_int}>".strip())
        else:
            chips.append(f"`{emoji} {role}`".strip())

    return " ".join(chips) if chips else "`Any`"


def _v14_header_table(task: dict[str, Any]) -> str:
    claimers = _claimers(task)
    cap = _capacity(task)
    priority = _priority(task)

    assignee_line = ", ".join(_mention(x) for x in claimers) if claimers else "No one has claimed this yet."

    return (
        "**Status**\n"
        f"{_v14_status_markdown(task)}\n"
        "**Priority**\n"
        f"`{priority}`\n\n"
        f"**Assignees ({len(claimers)}/{cap})**\n"
        f"{assignee_line}"
    )


def _v14_meta_table(task: dict[str, Any]) -> str:
    authors = _authors(task)
    roles = _v14_role_chips(task.get("job_role") or task.get("job_roles"))
    os_text = _os(task)
    engine = _engine(task)
    due = _v14_due_date(task)

    return (
        f"**Authors**\n{authors}\n\n"
        f"**Roles**\n{roles}\n\n"
        f"**OS**\n{os_text}\n\n"
        f"**Engine**\n{engine}\n\n"
        f"**Due Date**\n{due}"
    )


async def _v14_find_task(interaction: discord.Interaction, task_id: int | None = None) -> dict[str, Any] | None:
    from taskbot.db import get_task_by_message, get_task_by_thread

    if task_id:
        try:
            from taskbot.db import get_task
            task = get_task(int(task_id))
            if task:
                return task
        except Exception:
            pass

    if isinstance(interaction.channel, discord.Thread):
        task = get_task_by_thread(interaction.channel.id)
        if task:
            return task

    if interaction.message:
        task = get_task_by_message(interaction.message.id)
        if task:
            return task

    return None


async def _v14_safe_ephemeral(interaction: discord.Interaction, message: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        pass


async def _v14_safe_defer(interaction: discord.Interaction) -> bool:
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        return True
    except Exception:
        return False


class _V14ConfirmUnclaimView(discord.ui.View):
    def __init__(self, task_id: int) -> None:
        super().__init__(timeout=120)
        self.task_id = int(task_id)

    @discord.ui.button(label="Yes, unclaim", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        task = await _v14_find_task(interaction, self.task_id)
        if not task:
            await _v14_safe_ephemeral(interaction, "Could not find this task.")
            return

        if not await _v14_safe_defer(interaction):
            return

        from taskbot.db import remove_task_claim
        from taskbot.forum import sync_discord_task

        ok, message, updated = remove_task_claim(task["id"], interaction.user.id, interaction.user.id)
        if updated:
            await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(message or "You unclaimed this task.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await _v14_safe_ephemeral(interaction, "Canceled.")


class _V14TaskButton(discord.ui.Button):
    def __init__(
        self,
        *,
        task_id: int,
        action: str,
        label: str,
        style: discord.ButtonStyle,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            label=label,
            style=style,
            custom_id=f"taskbot_v14:{action}:{task_id}",
            disabled=disabled,
        )
        self.task_id = int(task_id)
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            await self._callback_impl(interaction)
        except Exception as exc:
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)
            await _v14_safe_ephemeral(interaction, "This task action failed. Check the bot terminal.")

    async def _callback_impl(self, interaction: discord.Interaction) -> None:
        task = await _v14_find_task(interaction, self.task_id)
        if not task:
            await _v14_safe_ephemeral(interaction, "Could not find this task in the database.")
            return

        if self.action == "edit":
            from taskbot.access import can_manage_task
            from taskbot.modals import TaskEditModal

            if not isinstance(interaction.user, discord.Member) or not can_manage_task(interaction.user, task):
                await _v14_safe_ephemeral(interaction, "Only admins or the task assigner who created this task can edit it.")
                return

            # Do not defer before a modal. send_modal must be the first response.
            await interaction.response.send_modal(TaskEditModal(interaction.client, task))  # type: ignore[arg-type]
            return

        if self.action == "unclaim":
            claimers = _claimers(task)
            if interaction.user.id not in claimers:
                await _v14_safe_ephemeral(interaction, "You have not claimed this task.")
                return
            await interaction.response.send_message(
                "Are you sure you want to unclaim this task?",
                view=_V14ConfirmUnclaimView(int(task["id"])),
                ephemeral=True,
            )
            return

        if self.action == "claim":
            if not interaction.guild:
                await _v14_safe_ephemeral(interaction, "Tasks can only be claimed inside a server.")
                return

            from taskbot.config import settings
            from taskbot.db import claim_task, count_active_assignments, get_profile
            from taskbot.forum import sync_discord_task

            if len(_claimers(task)) >= _capacity(task):
                await _v14_safe_ephemeral(interaction, "This task is already filled.")
                return

            active_count = count_active_assignments(interaction.user.id, interaction.guild.id)
            if active_count >= settings.max_active_assignments:
                await _v14_safe_ephemeral(
                    interaction,
                    f"You already have {active_count} active assignments. The limit is {settings.max_active_assignments}.",
                )
                return

            if not get_profile(interaction.guild.id, interaction.user.id):
                from taskbot.modals import ProfileEditModal
                await interaction.response.send_modal(ProfileEditModal(guild_id=interaction.guild.id, user_id=interaction.user.id))
                return

            if not await _v14_safe_defer(interaction):
                return

            ok, message, updated = claim_task(task["id"], interaction.user.id)
            if not ok:
                await interaction.followup.send(message, ephemeral=True)
                return

            if updated:
                await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
                try:
                    from taskbot.notifications import notify_claim
                    await notify_claim(interaction.client, updated, interaction.user)  # type: ignore[arg-type]
                except Exception:
                    pass
                await interaction.followup.send("You claimed this task. Your task profile card was sent to the assigner.", ephemeral=True)
            return

        if self.action in {"to_do", "in_progress", "review", "done", "archive"}:
            from taskbot.access import can_manage_task
            from taskbot.db import update_task
            from taskbot.forum import sync_discord_task

            if not isinstance(interaction.user, discord.Member) or not can_manage_task(interaction.user, task):
                await _v14_safe_ephemeral(interaction, "Only admins or the task assigner who created this task can change it.")
                return

            if not await _v14_safe_defer(interaction):
                return

            if self.action == "archive":
                currently_archived = bool(task.get("archived")) or _clean_str(task.get("status")).lower() == "archived"
                new_status = "To Do" if currently_archived else "Archived"
                updated = update_task(
                    task["id"],
                    interaction.user.id,
                    "archive_changed",
                    status=new_status,
                    archived=0 if currently_archived else 1,
                )
                if updated:
                    await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
                await interaction.followup.send("Task unarchived and moved to To Do." if currently_archived else "Task archived.", ephemeral=True)
                return

            status_map = {
                "to_do": "To Do",
                "in_progress": "In Progress",
                "review": "Review",
                "done": "Done",
            }
            status = status_map[self.action]
            updated = update_task(task["id"], interaction.user.id, "status_changed", status=status, archived=0)
            if updated:
                await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
            await interaction.followup.send(f"Task moved to **{status}**.", ephemeral=True)


class TaskV2View(_BaseLayoutView):  # type: ignore[misc, no-redef]
    def __init__(self, task: dict[str, Any], *, include_controls: bool = True) -> None:
        super().__init__(timeout=None)
        if not supports_components_v2():
            return

        container_cls = getattr(discord.ui, "Container")
        separator_cls = getattr(discord.ui, "Separator")
        action_row_cls = getattr(discord.ui, "ActionRow")

        c = container_cls()

        banner_url = _v14_banner_url(task)
        if banner_url and hasattr(discord.ui, "MediaGallery"):
            try:
                gallery = getattr(discord.ui, "MediaGallery")()
                gallery.add_item(banner_url)
                _add(c, gallery)
                _add(c, separator_cls(visible=True))
            except Exception:
                _add(c, _new_text_display("▔" * 40))
                _add(c, separator_cls(visible=True))
        else:
            _add(c, _new_text_display("▔" * 40))
            _add(c, separator_cls(visible=True))

        title = _clean_str(task.get("title"), "Untitled Task")
        description = _clean_str(task.get("description"), "No description provided.") or "No description provided."

        _add(c, _new_text_display(f"# {title}"))
        _add(c, _new_text_display(description))
        _add(c, separator_cls(visible=True))

        _add(c, _new_text_display(_v14_header_table(task)))
        _add(c, separator_cls(visible=True))
        _add(c, _new_text_display(_v14_meta_table(task)))
        _add(c, separator_cls(visible=True))

        if include_controls:
            task_id = int(task.get("id") or 0)
            claimers = _claimers(task)
            is_archived = bool(task.get("archived")) or _clean_str(task.get("status")).lower() == "archived"
            status = _clean_str(task.get("status"), "To Do").lower()
            user_claimed = False

            _add(c, _new_text_display("-# Change task status"))
            status_row = action_row_cls()
            for action, label, is_selected in [
                ("to_do", "To Do", status in {"to do", "todo"}),
                ("in_progress", "In Progress", status == "in progress"),
                ("review", "Review", status == "review"),
                ("done", "Done", status == "done"),
            ]:
                status_row.add_item(
                    _V14TaskButton(
                        task_id=task_id,
                        action=action,
                        label=label,
                        style=discord.ButtonStyle.primary if is_selected else discord.ButtonStyle.secondary,
                        disabled=is_archived,
                    )
                )
            _add(c, status_row)

            _add(c, _new_text_display("-# Claim, edit, or archive this post"))
            action_row = action_row_cls()
            can_claim = len(claimers) < _capacity(task) and not is_archived
            # The per-user claimed state is decided at click time. The static card
            # uses both Claim and Unclaim so either action is always reachable.
            action_row.add_item(
                _V14TaskButton(
                    task_id=task_id,
                    action="claim",
                    label="Claim",
                    style=discord.ButtonStyle.primary if can_claim else discord.ButtonStyle.secondary,
                    disabled=not can_claim,
                )
            )
            action_row.add_item(
                _V14TaskButton(
                    task_id=task_id,
                    action="unclaim",
                    label="Unclaim",
                    style=discord.ButtonStyle.danger if claimers and not is_archived else discord.ButtonStyle.secondary,
                    disabled=not claimers or is_archived,
                )
            )
            action_row.add_item(
                _V14TaskButton(
                    task_id=task_id,
                    action="edit",
                    label="Edit Post",
                    style=discord.ButtonStyle.secondary,
                    disabled=is_archived,
                )
            )
            action_row.add_item(
                _V14TaskButton(
                    task_id=task_id,
                    action="archive",
                    label="Unarchive" if is_archived else "Archive",
                    style=discord.ButtonStyle.secondary,
                    disabled=False,
                )
            )
            _add(c, action_row)

        self.add_item(c)


def task_message_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    if supports_components_v2():
        kwargs: dict[str, Any] = {"view": TaskV2View(task, include_controls=include_controls)}
        banner_file = _v14_banner_file(task)
        if banner_file is not None:
            kwargs["file"] = banner_file
        return kwargs

    from taskbot.embeds import task_embed
    from taskbot.views import TaskControls

    return {"embed": task_embed(task), "view": TaskControls() if include_controls else None}


def task_edit_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    if supports_components_v2():
        # Do not clear attachments here; the default banner is an attachment
        # created with the starter message and must be preserved on edits.
        return {
            "content": None,
            "embeds": [],
            "view": TaskV2View(task, include_controls=include_controls),
        }

    from taskbot.embeds import task_embed
    from taskbot.views import TaskControls

    return {"embed": task_embed(task), "view": TaskControls() if include_controls else None}

# ---- v15 default banner + role mention + direct action override ----

from pathlib import Path as _TaskbotPath

try:
    from taskbot.constants import JOB_ROLE_EMOJIS as _V15_JOB_ROLE_EMOJIS
except Exception:
    _V15_JOB_ROLE_EMOJIS = {}

try:
    from taskbot.constants import JOB_ROLE_MENTION_IDS as _V15_JOB_ROLE_MENTION_IDS
except Exception:
    _V15_JOB_ROLE_MENTION_IDS = {}

_V15_BANNER_FILENAME = "taskbot_default_banner.png"


def _v15_assets_banner_path() -> _TaskbotPath:
    return _TaskbotPath(__file__).resolve().parent / "assets" / "banner.png"


def _v15_valid_remote_url(value: object) -> bool:
    text = _clean_str(value)
    return text.startswith("https://") or text.startswith("http://")


def _v15_default_banner_file(task: dict[str, Any]) -> discord.File | None:
    if _v15_valid_remote_url(task.get("thumbnail_url") or task.get("banner_url")):
        return None
    path = _v15_assets_banner_path()
    if not path.exists():
        return None
    return discord.File(str(path), filename=_V15_BANNER_FILENAME)


def _v15_banner_ref(task: dict[str, Any]) -> str:
    external = _clean_str(task.get("thumbnail_url") or task.get("banner_url"))
    if _v15_valid_remote_url(external):
        return external
    if _v15_assets_banner_path().exists():
        return f"attachment://{_V15_BANNER_FILENAME}"
    return ""


def _v15_role_line(task: dict[str, Any]) -> str:
    roles = _csv(task.get("job_role") or task.get("job_roles"))
    if not roles:
        return "Any"

    parts: list[str] = []
    seen: set[str] = set()
    for role in roles:
        key = role.strip()
        if not key or key.lower() in seen:
            continue
        seen.add(key.lower())
        emoji = _V15_JOB_ROLE_EMOJIS.get(key, "")
        role_id = _V15_JOB_ROLE_MENTION_IDS.get(key)
        label = f"<@&{int(role_id)}>" if role_id else key
        parts.append(f"{emoji} {label}".strip())

    return "\n".join(parts) if parts else "Any"


def _v15_status_text(task: dict[str, Any]) -> str:
    status = _clean_str(task.get("status"), "To Do")
    low = status.lower()
    if low in {"to do", "todo"}:
        return "```diff\n+ To Do\n```"
    if low in {"in progress", "progress"}:
        return "```fix\nIn Progress\n```"
    if low == "review":
        return "```css\n[Review]\n```"
    if low == "done":
        return "```ini\n[Done]\n```"
    if low == "archived" or bool(task.get("archived")):
        return "```elm\nArchived\n```"
    return f"```ini\n[{status}]\n```"


def _v15_priority_text(task: dict[str, Any]) -> str:
    return f"`{_priority(task)}`"


def _v15_claimers(task: dict[str, Any]) -> list[int]:
    return _claimers(task)


def _v15_is_archived(task: dict[str, Any]) -> bool:
    return bool(task.get("archived")) or _clean_str(task.get("status")).lower() == "archived"


def _v15_has_user_claimed(task: dict[str, Any], user_id: int) -> bool:
    try:
        return int(user_id) in [int(x) for x in _v15_claimers(task)]
    except Exception:
        return False


def _v15_editable_by(interaction: discord.Interaction, task: dict[str, Any]) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    try:
        from taskbot.access import can_manage_task
        return bool(can_manage_task(interaction.user, task))
    except Exception:
        return int(task.get("creator_id") or 0) == int(interaction.user.id)


async def _v15_get_task(interaction: discord.Interaction, task_id: int) -> dict[str, Any] | None:
    from taskbot.db import get_task_by_message, get_task_by_thread

    task = None
    if isinstance(interaction.channel, discord.Thread):
        task = get_task_by_thread(interaction.channel.id)
    if task is None and interaction.message:
        task = get_task_by_message(interaction.message.id)
    return task


class _V15UnclaimConfirmView(discord.ui.View):
    def __init__(self, task_id: int, user_id: int) -> None:
        super().__init__(timeout=120)
        self.task_id = int(task_id)
        self.user_id = int(user_id)

    @discord.ui.button(label="Confirm Unclaim", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if int(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Only the person who opened this confirmation can use it.", ephemeral=True)
            return
        from taskbot.db import unclaim_task
        from taskbot.forum import sync_discord_task
        await interaction.response.defer(ephemeral=True)
        ok, message, updated = unclaim_task(self.task_id, self.user_id)
        if updated:
            await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Cancelled.", view=None)


class _V15TaskButton(discord.ui.Button):
    def __init__(self, *, task: dict[str, Any], action: str, label: str, style: discord.ButtonStyle, disabled: bool = False) -> None:
        super().__init__(label=label, style=style, custom_id=f"taskbot_v15:{action}:{int(task.get('id') or 0)}", disabled=disabled)
        self.action = action
        self.task_id = int(task.get("id") or 0)

    async def callback(self, interaction: discord.Interaction) -> None:
        task = await _v15_get_task(interaction, self.task_id)
        if not task:
            await interaction.response.send_message("Could not find this task in the database.", ephemeral=True)
            return
        action = self.action

        if action in {"todo", "progress", "review", "done", "archive", "unarchive"}:
            if not _v15_editable_by(interaction, task):
                await interaction.response.send_message("Only admins or the task assigner who created this task can edit/archive it.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            from taskbot.db import update_task
            from taskbot.forum import sync_discord_task
            status_map = {"todo": "To Do", "progress": "In Progress", "review": "Review", "done": "Done", "archive": "Archived", "unarchive": "To Do"}
            archived = 1 if action == "archive" else 0
            updated = update_task(task["id"], interaction.user.id, "status_changed", status=status_map[action], archived=archived)
            if updated:
                await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
            await interaction.followup.send(f"Task moved to **{status_map[action]}**.", ephemeral=True)
            return

        if action == "claim":
            if not interaction.guild:
                await interaction.response.send_message("Tasks can only be claimed inside a server.", ephemeral=True)
                return
            from taskbot.config import settings
            from taskbot.db import claim_task, count_active_assignments, get_profile
            from taskbot.forum import sync_discord_task
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
            if updated:
                await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
                try:
                    from taskbot.notifications import notify_claim
                    await notify_claim(interaction.client, updated, interaction.user)  # type: ignore[arg-type]
                except Exception:
                    pass
            await interaction.followup.send(message, ephemeral=True)
            return

        if action == "unclaim":
            if not _v15_has_user_claimed(task, interaction.user.id):
                await interaction.response.send_message("You have not claimed this task.", ephemeral=True)
                return
            await interaction.response.send_message("Are you sure you want to unclaim this task?", view=_V15UnclaimConfirmView(int(task["id"]), int(interaction.user.id)), ephemeral=True)
            return

        if action == "edit":
            if not _v15_editable_by(interaction, task):
                await interaction.response.send_message("Only admins or the task assigner who created this task can edit it.", ephemeral=True)
                return
            from taskbot.modals import TaskEditModal
            await interaction.response.send_modal(TaskEditModal(interaction.client, task))  # type: ignore[arg-type]
            return

        await interaction.response.send_message("Unknown task action.", ephemeral=True)


class TaskV2View(_BaseLayoutView):  # type: ignore[misc, no-redef]
    def __init__(self, task: dict[str, Any], *, include_controls: bool = True) -> None:
        super().__init__(timeout=None)
        if not supports_components_v2():
            return
        container_cls = getattr(discord.ui, "Container")
        separator_cls = getattr(discord.ui, "Separator")
        action_row_cls = getattr(discord.ui, "ActionRow", None)
        media_gallery_cls = getattr(discord.ui, "MediaGallery", None)
        c = container_cls()

        banner = _v15_banner_ref(task)
        if banner and media_gallery_cls:
            try:
                gallery = media_gallery_cls()
                gallery.add_item(banner)
                _add(c, gallery)
                _add(c, separator_cls(visible=True))
            except Exception:
                pass

        title = _clip(task.get("title") or "Untitled Task", 100)
        description = _clip(task.get("description") or "No description provided.", 1600)
        _add(c, _new_text_display(f"# {title}\n\n{description}"))
        _add(c, separator_cls(visible=True))

        claimers = _v15_claimers(task)
        cap = _capacity(task)
        assignees = "\n".join(_mention(x) for x in claimers) if claimers else "No one has claimed this yet."
        _add(c, _new_text_display(f"**Status**\n{_v15_status_text(task)}\n**Priority**\n{_v15_priority_text(task)}\n\n**Assignees ({len(claimers)}/{cap})**\n{assignees}"))
        _add(c, separator_cls(visible=True))
        _add(c, _new_text_display(f"**Authors**\n{_authors(task)}\n\n**Roles**\n{_v15_role_line(task)}\n\n**OS**\n{_os(task)}\n\n**Engine**\n{_engine(task)}\n\n**Due Date**\n{_clean_str(task.get('due_date'), 'No due date')}"))

        gallery_urls = [u for u in _csv(task.get("gallery_urls") or task.get("image_urls") or task.get("attachment_urls")) if _v15_valid_remote_url(u)]
        if gallery_urls and media_gallery_cls:
            try:
                gallery = media_gallery_cls()
                for url in gallery_urls[:10]:
                    gallery.add_item(url)
                _add(c, separator_cls(visible=True))
                _add(c, gallery)
            except Exception:
                pass

        if include_controls and action_row_cls:
            archived = _v15_is_archived(task)
            status = _clean_str(task.get("status"), "To Do").lower()
            _add(c, separator_cls(visible=True))
            _add(c, _new_text_display("-# Change status"))
            row1 = action_row_cls()
            row1.add_item(_V15TaskButton(task=task, action="todo", label="To Do", style=discord.ButtonStyle.primary if status in {"to do", "todo"} else discord.ButtonStyle.secondary, disabled=archived))
            row1.add_item(_V15TaskButton(task=task, action="progress", label="In Progress", style=discord.ButtonStyle.primary if status == "in progress" else discord.ButtonStyle.secondary, disabled=archived))
            row1.add_item(_V15TaskButton(task=task, action="review", label="Review", style=discord.ButtonStyle.primary if status == "review" else discord.ButtonStyle.secondary, disabled=archived))
            row1.add_item(_V15TaskButton(task=task, action="done", label="Done", style=discord.ButtonStyle.primary if status == "done" else discord.ButtonStyle.secondary, disabled=archived))
            _add(c, row1)
            row2 = action_row_cls()
            row2.add_item(_V15TaskButton(task=task, action="claim", label="Claim", style=discord.ButtonStyle.primary, disabled=archived))
            row2.add_item(_V15TaskButton(task=task, action="unclaim", label="Unclaim", style=discord.ButtonStyle.danger, disabled=archived))
            row2.add_item(_V15TaskButton(task=task, action="edit", label="Edit Post", style=discord.ButtonStyle.secondary, disabled=archived))
            row2.add_item(_V15TaskButton(task=task, action="unarchive" if archived else "archive", label="Unarchive" if archived else "Archive", style=discord.ButtonStyle.secondary))
            _add(c, row2)

        self.add_item(c)


def task_message_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"view": TaskV2View(task, include_controls=include_controls)}
    banner_file = _v15_default_banner_file(task)
    if banner_file is not None:
        kwargs["file"] = banner_file
    return kwargs


def task_edit_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"content": None, "embed": None, "view": TaskV2View(task, include_controls=include_controls)}
    banner_file = _v15_default_banner_file(task)
    if banner_file is not None:
        kwargs["attachments"] = [banner_file]
    return kwargs

# ---- end v15 default banner + role mention + direct action override ----

# ---- v16 valid components v2 layout + banner + case-insensitive roles ----

from pathlib import Path as _V16Path
from datetime import datetime as _V16DateTime, time as _V16Time, timezone as _V16Timezone

_V16_BANNER_FILENAME = "taskbot_default_banner.png"


def _v16_banner_path() -> _V16Path:
    return _V16Path(__file__).resolve().parent / "assets" / "banner.png"


def _v16_remote_url(value: object) -> str:
    text = _clean_str(value)
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return ""


def _v16_banner_ref(task: dict[str, Any]) -> str:
    explicit = _v16_remote_url(task.get("thumbnail_url") or task.get("banner_url"))
    if explicit:
        return explicit
    if _v16_banner_path().exists():
        return f"attachment://{_V16_BANNER_FILENAME}"
    return ""


def _v16_banner_file(task: dict[str, Any]) -> discord.File | None:
    if _v16_remote_url(task.get("thumbnail_url") or task.get("banner_url")):
        return None
    path = _v16_banner_path()
    if path.exists():
        return discord.File(str(path), filename=_V16_BANNER_FILENAME)
    return None


def _v16_status(task: dict[str, Any]) -> str:
    status = _clean_str(task.get("status"), "To Do")
    low = status.lower()
    if bool(task.get("archived")) or low == "archived":
        return "```elm\nArchived\n```"
    if low in {"to do", "todo"}:
        return "```diff\n+ To Do\n```"
    if low in {"in progress", "progress"}:
        return "```fix\nIn Progress\n```"
    if low == "review":
        return "```css\n[Review]\n```"
    if low == "done":
        return "```ini\n[Done]\n```"
    return f"```ini\n[{status}]\n```"


def _v16_due(task: dict[str, Any]) -> str:
    raw = _clean_str(task.get("due_date"))
    if not raw:
        return "No due date"
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = _V16DateTime.strptime(raw[:19], fmt)
            if fmt == "%Y-%m-%d":
                dt = _V16DateTime.combine(dt.date(), _V16Time(hour=12))
            dt = dt.replace(tzinfo=_V16Timezone.utc)
            ts = int(dt.timestamp())
            return f"<t:{ts}:D>\n<t:{ts}:R>"
        except Exception:
            pass
    return raw


def _v16_role_line(task: dict[str, Any]) -> str:
    roles = _csv(task.get("job_role") or task.get("job_roles"))
    if not roles:
        return "Any"

    try:
        from taskbot.constants import JOB_ROLE_EMOJIS, JOB_ROLE_MENTION_IDS
    except Exception:
        JOB_ROLE_EMOJIS = {}
        JOB_ROLE_MENTION_IDS = {}

    emoji_by_lower = {str(k).lower(): v for k, v in JOB_ROLE_EMOJIS.items()}
    id_by_lower = {str(k).lower(): v for k, v in JOB_ROLE_MENTION_IDS.items()}

    out: list[str] = []
    seen: set[str] = set()
    for role in roles:
        key = _clean_str(role)
        low = key.lower()
        if not key or low in seen:
            continue
        seen.add(low)

        emoji = emoji_by_lower.get(low, "")
        role_id = id_by_lower.get(low)
        try:
            role_id_int = int(role_id)
        except Exception:
            role_id_int = 0

        mention = f"<@&{role_id_int}>" if role_id_int else key
        out.append(f"{emoji} {mention}".strip())

    return "\n".join(out) if out else "Any"


def _v16_archived(task: dict[str, Any]) -> bool:
    return bool(task.get("archived")) or _clean_str(task.get("status")).lower() == "archived"


def _v16_section(*texts: str, accessory: Any | None = None) -> Any | None:
    # Valid Section: 1-3 TextDisplay children plus optional accessory.
    # It is not a general grid and cannot contain nested Containers.
    if not hasattr(discord.ui, "Section"):
        return None

    text_items = [_new_text_display(_clip(t or "—", 4000)) for t in texts if _clean_str(t)]
    if not text_items:
        text_items = [_new_text_display("—")]

    section_cls = getattr(discord.ui, "Section")
    try:
        if accessory is not None:
            return section_cls(*text_items[:3], accessory=accessory)
        return section_cls(*text_items[:3])
    except TypeError:
        try:
            section = section_cls(accessory=accessory) if accessory is not None else section_cls()
            for item in text_items[:3]:
                section.add_item(item)
            return section
        except Exception:
            return None
    except Exception:
        return None


async def _v16_find_task(interaction: discord.Interaction, task_id: int) -> dict[str, Any] | None:
    from taskbot.db import get_task_by_message, get_task_by_thread

    if isinstance(interaction.channel, discord.Thread):
        task = get_task_by_thread(interaction.channel.id)
        if task:
            return task

    if interaction.message:
        task = get_task_by_message(interaction.message.id)
        if task:
            return task

    try:
        from taskbot.db import search_tasks
        guild_id = interaction.guild.id if interaction.guild else 0
        for task in search_tasks(guild_id=guild_id, include_archived=True, limit=200):
            if int(task.get("id") or 0) == int(task_id):
                return task
    except Exception:
        pass

    return None


def _v16_can_manage(interaction: discord.Interaction, task: dict[str, Any]) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    try:
        from taskbot.access import can_manage_task
        return bool(can_manage_task(interaction.user, task))
    except Exception:
        return int(task.get("creator_id") or 0) == int(interaction.user.id)


class _V16UnclaimConfirm(discord.ui.View):
    def __init__(self, task_id: int, user_id: int) -> None:
        super().__init__(timeout=120)
        self.task_id = int(task_id)
        self.user_id = int(user_id)

    @discord.ui.button(label="Confirm Unclaim", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if int(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Only the user who opened this confirmation can use it.", ephemeral=True)
            return

        from taskbot.db import unclaim_task
        from taskbot.forum import sync_discord_task

        await interaction.response.defer(ephemeral=True)
        ok, message, updated = unclaim_task(self.task_id, self.user_id)
        if updated:
            await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(message or "You unclaimed this task.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Cancelled.", view=None)


class _V16TaskButton(discord.ui.Button):
    def __init__(self, task: dict[str, Any], action: str, label: str, style: discord.ButtonStyle, disabled: bool = False) -> None:
        super().__init__(
            label=label,
            style=style,
            custom_id=f"taskbot_v16:{action}:{int(task.get('id') or 0)}",
            disabled=disabled,
        )
        self.task_id = int(task.get("id") or 0)
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        task = await _v16_find_task(interaction, self.task_id)
        if not task:
            await interaction.response.send_message("Could not find this task in the database.", ephemeral=True)
            return

        action = self.action

        if action in {"todo", "progress", "review", "done", "archive", "unarchive"}:
            if not _v16_can_manage(interaction, task):
                await interaction.response.send_message("Only admins or the task assigner who created this task can change it.", ephemeral=True)
                return

            from taskbot.db import update_task
            from taskbot.forum import sync_discord_task

            status_map = {
                "todo": "To Do",
                "progress": "In Progress",
                "review": "Review",
                "done": "Done",
                "archive": "Archived",
                "unarchive": "To Do",
            }
            archived = 1 if action == "archive" else 0

            await interaction.response.defer(ephemeral=True)
            updated = update_task(task["id"], interaction.user.id, "status_changed", status=status_map[action], archived=archived)
            if updated:
                await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
            await interaction.followup.send(f"Task moved to **{status_map[action]}**.", ephemeral=True)
            return

        if action == "edit":
            if not _v16_can_manage(interaction, task):
                await interaction.response.send_message("Only admins or the task assigner who created this task can edit it.", ephemeral=True)
                return

            from taskbot.modals import TaskEditModal
            await interaction.response.send_modal(TaskEditModal(interaction.client, task))  # type: ignore[arg-type]
            return

        if action == "claim":
            if not interaction.guild:
                await interaction.response.send_message("Tasks can only be claimed inside a server.", ephemeral=True)
                return

            from taskbot.config import settings
            from taskbot.db import claim_task, count_active_assignments, get_profile
            from taskbot.forum import sync_discord_task

            if len(_claimers(task)) >= _capacity(task):
                await interaction.response.send_message("This task is already filled.", ephemeral=True)
                return

            active_count = count_active_assignments(interaction.user.id, interaction.guild.id)
            if active_count >= settings.max_active_assignments:
                await interaction.response.send_message(
                    f"You already have {active_count} active assignments. The limit is {settings.max_active_assignments}.",
                    ephemeral=True,
                )
                return

            if not get_profile(interaction.guild.id, interaction.user.id):
                from taskbot.modals import ProfileEditModal
                await interaction.response.send_modal(ProfileEditModal(guild_id=interaction.guild.id, user_id=interaction.user.id))
                return

            await interaction.response.defer(ephemeral=True)
            ok, message, updated = claim_task(task["id"], interaction.user.id)
            if updated:
                await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
                try:
                    from taskbot.notifications import notify_claim
                    await notify_claim(interaction.client, updated, interaction.user)  # type: ignore[arg-type]
                except Exception:
                    pass
            await interaction.followup.send(message, ephemeral=True)
            return

        if action == "unclaim":
            claimers = [int(x) for x in _claimers(task)]
            if int(interaction.user.id) not in claimers:
                await interaction.response.send_message("You have not claimed this task.", ephemeral=True)
                return

            await interaction.response.send_message(
                "Are you sure you want to unclaim this task?",
                view=_V16UnclaimConfirm(int(task["id"]), int(interaction.user.id)),
                ephemeral=True,
            )
            return


class TaskV2View(_BaseLayoutView):  # type: ignore[misc, no-redef]
    def __init__(self, task: dict[str, Any], *, include_controls: bool = True) -> None:
        super().__init__(timeout=None)

        if not supports_components_v2():
            return

        container_cls = getattr(discord.ui, "Container")
        separator_cls = getattr(discord.ui, "Separator")
        action_row_cls = getattr(discord.ui, "ActionRow")
        media_gallery_cls = getattr(discord.ui, "MediaGallery", None)

        c = container_cls()

        banner = _v16_banner_ref(task)
        if banner and media_gallery_cls:
            try:
                gallery = media_gallery_cls()
                gallery.add_item(banner)
                _add(c, gallery)
                _add(c, separator_cls(visible=True))
            except Exception:
                pass

        title = _clip(task.get("title") or "Untitled Task", 180)
        description = _clip(task.get("description") or "No description provided.", 1800)
        _add(c, _new_text_display(f"# {title}\n\n{description}"))
        _add(c, separator_cls(visible=True))

        claimers = _claimers(task)
        cap = _capacity(task)
        assignees = "\n".join(_mention(x) for x in claimers) if claimers else "No one has claimed this yet."

        row1 = _v16_section(
            f"**Status**\n{_v16_status(task)}\n**Priority**\n`{_priority(task)}`",
            f"**Assignees ({len(claimers)}/{cap})**\n{assignees}",
        )
        if row1 is not None:
            _add(c, row1)
        else:
            _add(c, _new_text_display(f"**Status**\n{_v16_status(task)}\n**Priority**\n`{_priority(task)}`\n\n**Assignees ({len(claimers)}/{cap})**\n{assignees}"))

        _add(c, separator_cls(visible=True))

        row2 = _v16_section(
            f"**Authors**\n{_authors(task)}\n\n**Roles**\n{_v16_role_line(task)}",
            f"**OS**\n{_os(task)}\n\n**Engine**\n{_engine(task)}",
            f"**Due Date**\n{_v16_due(task)}",
        )
        if row2 is not None:
            _add(c, row2)
        else:
            _add(c, _new_text_display(
                f"**Authors**\n{_authors(task)}\n\n"
                f"**Roles**\n{_v16_role_line(task)}\n\n"
                f"**OS**\n{_os(task)}\n\n"
                f"**Engine**\n{_engine(task)}\n\n"
                f"**Due Date**\n{_v16_due(task)}"
            ))

        gallery_urls = [u for u in _csv(task.get("gallery_urls") or task.get("image_urls") or task.get("attachment_urls")) if _v16_remote_url(u)]
        if gallery_urls and media_gallery_cls:
            try:
                gallery = media_gallery_cls()
                for url in gallery_urls[:10]:
                    gallery.add_item(url)
                _add(c, separator_cls(visible=True))
                _add(c, gallery)
            except Exception:
                pass

        if include_controls:
            archived = _v16_archived(task)
            status = _clean_str(task.get("status"), "To Do").lower()

            _add(c, separator_cls(visible=True))
            _add(c, _new_text_display("-# Change status"))

            row1_buttons = action_row_cls()
            for action, label, selected in (
                ("todo", "To Do", status in {"to do", "todo"} and not archived),
                ("progress", "In Progress", status == "in progress" and not archived),
                ("review", "Review", status == "review" and not archived),
                ("done", "Done", status == "done" and not archived),
            ):
                row1_buttons.add_item(
                    _V16TaskButton(
                        task,
                        action,
                        label,
                        discord.ButtonStyle.primary if selected else discord.ButtonStyle.secondary,
                        disabled=archived,
                    )
                )
            _add(c, row1_buttons)

            _add(c, _new_text_display("-# Claim, edit, or archive this post"))

            row2_buttons = action_row_cls()
            row2_buttons.add_item(_V16TaskButton(task, "claim", "Claim", discord.ButtonStyle.primary, disabled=archived))
            row2_buttons.add_item(_V16TaskButton(task, "unclaim", "Unclaim", discord.ButtonStyle.danger, disabled=archived or not bool(claimers)))
            row2_buttons.add_item(_V16TaskButton(task, "edit", "Edit Post", discord.ButtonStyle.secondary, disabled=archived))
            row2_buttons.add_item(_V16TaskButton(task, "unarchive" if archived else "archive", "Unarchive" if archived else "Archive", discord.ButtonStyle.secondary))
            _add(c, row2_buttons)

        self.add_item(c)


def task_message_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    # In discord.py, LayoutView/TextDisplay/Container causes the library to send
    # the IS_COMPONENTS_V2 flag. Do not pass is_components_v2=True; that is not
    # a discord.py keyword and ForumChannel.create_thread does not accept it.
    kwargs: dict[str, Any] = {
        "view": TaskV2View(task, include_controls=include_controls),
    }
    banner_file = _v16_banner_file(task)
    if banner_file is not None:
        kwargs["file"] = banner_file
    return kwargs


def task_edit_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "content": None,
        "embed": None,
        "view": TaskV2View(task, include_controls=include_controls),
    }
    banner_file = _v16_banner_file(task)
    if banner_file is not None:
        try:
            kwargs["attachments"] = [banner_file]
        except Exception:
            pass
    return kwargs

# ---- end v16 valid components v2 layout + banner + case-insensitive roles ----

# ---- v17 banner media + claim guard + summary columns ----

from pathlib import Path as _V17Path
from datetime import datetime as _V17DateTime, time as _V17Time, timezone as _V17Timezone

_V17_BANNER_FILENAME = "taskbot_default_banner.png"


def _v17_banner_path() -> _V17Path:
    return _V17Path(__file__).resolve().parent / "assets" / "banner.png"


def _v17_remote_url(value: object) -> str:
    text = _clean_str(value)
    return text if text.startswith(("https://", "http://")) else ""


def _v17_banner_ref(task: dict[str, Any]) -> str:
    explicit = _v17_remote_url(task.get("thumbnail_url") or task.get("banner_url"))
    if explicit:
        return explicit
    return f"attachment://{_V17_BANNER_FILENAME}" if _v17_banner_path().exists() else ""


def _v17_banner_file(task: dict[str, Any]) -> discord.File | None:
    if _v17_remote_url(task.get("thumbnail_url") or task.get("banner_url")):
        return None
    path = _v17_banner_path()
    if path.exists():
        return discord.File(str(path), filename=_V17_BANNER_FILENAME)
    return None


def _v17_add_media_gallery(container: Any, image_url: str) -> bool:
    if not image_url or not hasattr(discord.ui, "MediaGallery"):
        return False

    gallery_cls = getattr(discord.ui, "MediaGallery")
    gallery = gallery_cls()

    item_candidates: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    item_candidates.append(("add_item_args", (image_url,), {}))
    item_candidates.append(("add_item_url_kw", (), {"url": image_url}))
    item_candidates.append(("add_item_media_kw", (), {"media": image_url}))

    media_item_cls = (
        getattr(discord.ui, "MediaGalleryItem", None)
        or getattr(discord, "MediaGalleryItem", None)
    )
    unfurled_cls = (
        getattr(discord.ui, "UnfurledMediaItem", None)
        or getattr(discord, "UnfurledMediaItem", None)
    )

    if media_item_cls is not None:
        for args, kwargs in (
            ((image_url,), {}),
            ((), {"url": image_url}),
            ((), {"media": image_url}),
        ):
            try:
                item_candidates.append(("media_item", (media_item_cls(*args, **kwargs),), {}))
            except Exception:
                pass

        if unfurled_cls is not None:
            for args, kwargs in (
                ((image_url,), {}),
                ((), {"url": image_url}),
            ):
                try:
                    media = unfurled_cls(*args, **kwargs)
                    item_candidates.append(("unfurled_item", (media_item_cls(media=media),), {}))
                except Exception:
                    pass

    for _name, args, kwargs in item_candidates:
        try:
            gallery.add_item(*args, **kwargs)
            _add(container, gallery)
            return True
        except Exception:
            continue

    return False


def _v17_status_label(task: dict[str, Any]) -> str:
    status = _clean_str(task.get("status"), "To Do")
    if bool(task.get("archived")) or status.lower() == "archived":
        return "Archived"
    return status


def _v17_status_markdown(task: dict[str, Any]) -> str:
    status = _v17_status_label(task)
    low = status.lower()
    if low == "archived":
        return "```elm\nArchived\n```"
    if low in {"to do", "todo"}:
        return "```diff\n+ To Do\n```"
    if low == "in progress":
        return "```fix\nIn Progress\n```"
    if low == "review":
        return "```css\n[Review]\n```"
    if low == "done":
        return "```ini\n[Done]\n```"
    return f"```ini\n[{status}]\n```"


def _v17_due(task: dict[str, Any]) -> str:
    raw = _clean_str(task.get("due_date"))
    if not raw:
        return "No due date"
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = _V17DateTime.strptime(raw[:19], fmt)
            if fmt == "%Y-%m-%d":
                dt = _V17DateTime.combine(dt.date(), _V17Time(hour=12))
            dt = dt.replace(tzinfo=_V17Timezone.utc)
            ts = int(dt.timestamp())
            return f"<t:{ts}:D>\n<t:{ts}:R>"
        except Exception:
            pass
    return raw


def _v17_role_line(task: dict[str, Any]) -> str:
    roles = _csv(task.get("job_role") or task.get("job_roles"))
    if not roles:
        return "Any"

    try:
        from taskbot.constants import JOB_ROLE_EMOJIS, JOB_ROLE_MENTION_IDS
    except Exception:
        JOB_ROLE_EMOJIS = {}
        JOB_ROLE_MENTION_IDS = {}

    emoji_by_lower = {str(k).lower(): v for k, v in JOB_ROLE_EMOJIS.items()}
    id_by_lower = {str(k).lower(): v for k, v in JOB_ROLE_MENTION_IDS.items()}

    out: list[str] = []
    seen: set[str] = set()
    for role in roles:
        key = _clean_str(role)
        low = key.lower()
        if not key or low in seen:
            continue
        seen.add(low)

        emoji = emoji_by_lower.get(low, "")
        role_id = id_by_lower.get(low)
        try:
            mention = f"<@&{int(role_id)}>" if role_id else key
        except Exception:
            mention = key
        out.append(f"{emoji} {mention}".strip())

    return "\n".join(out) if out else "Any"


def _v17_archived(task: dict[str, Any]) -> bool:
    return bool(task.get("archived")) or _clean_str(task.get("status")).lower() == "archived"


async def _v17_find_task(interaction: discord.Interaction, task_id: int) -> dict[str, Any] | None:
    from taskbot.db import get_task_by_message, get_task_by_thread

    if isinstance(interaction.channel, discord.Thread):
        task = get_task_by_thread(interaction.channel.id)
        if task:
            return task

    if interaction.message:
        task = get_task_by_message(interaction.message.id)
        if task:
            return task

    try:
        from taskbot.db import search_tasks
        guild_id = interaction.guild.id if interaction.guild else 0
        for task in search_tasks(guild_id=guild_id, include_archived=True, limit=250):
            if int(task.get("id") or 0) == int(task_id):
                return task
    except Exception:
        pass

    return None


def _v17_can_manage(interaction: discord.Interaction, task: dict[str, Any]) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    try:
        from taskbot.access import can_manage_task
        return bool(can_manage_task(interaction.user, task))
    except Exception:
        return int(task.get("creator_id") or 0) == int(interaction.user.id)


class _V17UnclaimConfirm(discord.ui.View):
    def __init__(self, task_id: int, user_id: int) -> None:
        super().__init__(timeout=120)
        self.task_id = int(task_id)
        self.user_id = int(user_id)

    @discord.ui.button(label="Confirm Unclaim", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if int(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Only the user who opened this confirmation can use it.", ephemeral=True)
            return

        from taskbot.db import unclaim_task
        from taskbot.forum import sync_discord_task

        await interaction.response.defer(ephemeral=True)
        ok, message, updated = unclaim_task(self.task_id, self.user_id)
        if updated:
            await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
        await interaction.followup.send(message or "You unclaimed this task.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Cancelled.", view=None)


class _V17TaskButton(discord.ui.Button):
    def __init__(self, task: dict[str, Any], action: str, label: str, style: discord.ButtonStyle, disabled: bool = False) -> None:
        super().__init__(
            label=label,
            style=style,
            custom_id=f"taskbot_v17:{action}:{int(task.get('id') or 0)}",
            disabled=disabled,
        )
        self.task_id = int(task.get("id") or 0)
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        task = await _v17_find_task(interaction, self.task_id)
        if not task:
            await interaction.response.send_message("Could not find this task in the database.", ephemeral=True)
            return

        action = self.action
        claimers = [int(x) for x in _claimers(task)]
        user_id = int(interaction.user.id)

        if action == "claim":
            if user_id in claimers:
                await interaction.response.send_message("You already claimed this task.", ephemeral=True)
                return

            if len(claimers) >= _capacity(task):
                await interaction.response.send_message("This task is already filled.", ephemeral=True)
                return

            if _v17_archived(task):
                await interaction.response.send_message("This task is archived and cannot be claimed.", ephemeral=True)
                return

            if not interaction.guild:
                await interaction.response.send_message("Tasks can only be claimed inside a server.", ephemeral=True)
                return

            from taskbot.config import settings
            from taskbot.db import claim_task, count_active_assignments, get_profile
            from taskbot.forum import sync_discord_task

            active_count = count_active_assignments(user_id, interaction.guild.id)
            if active_count >= settings.max_active_assignments:
                await interaction.response.send_message(
                    f"You already have {active_count} active assignments. The limit is {settings.max_active_assignments}.",
                    ephemeral=True,
                )
                return

            if not get_profile(interaction.guild.id, user_id):
                from taskbot.modals import ProfileEditModal
                await interaction.response.send_modal(ProfileEditModal(guild_id=interaction.guild.id, user_id=user_id))
                return

            await interaction.response.defer(ephemeral=True)
            ok, message, updated = claim_task(task["id"], user_id)
            if updated:
                await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
                try:
                    from taskbot.notifications import notify_claim
                    await notify_claim(interaction.client, updated, interaction.user)  # type: ignore[arg-type]
                except Exception:
                    pass
            await interaction.followup.send(message or "You claimed this task.", ephemeral=True)
            return

        if action == "unclaim":
            if user_id not in claimers:
                await interaction.response.send_message("You have not claimed this task, so you cannot unclaim it.", ephemeral=True)
                return

            if _v17_archived(task):
                await interaction.response.send_message("This task is archived.", ephemeral=True)
                return

            await interaction.response.send_message(
                "Are you sure you want to unclaim this task?",
                view=_V17UnclaimConfirm(int(task["id"]), user_id),
                ephemeral=True,
            )
            return

        if action in {"todo", "progress", "review", "done", "archive", "unarchive"}:
            if not _v17_can_manage(interaction, task):
                await interaction.response.send_message("Only admins or the task assigner who created this task can change it.", ephemeral=True)
                return

            from taskbot.db import update_task
            from taskbot.forum import sync_discord_task

            status_map = {
                "todo": "To Do",
                "progress": "In Progress",
                "review": "Review",
                "done": "Done",
                "archive": "Archived",
                "unarchive": "To Do",
            }
            archived = 1 if action == "archive" else 0

            await interaction.response.defer(ephemeral=True)
            updated = update_task(task["id"], user_id, "status_changed", status=status_map[action], archived=archived)
            if updated:
                await sync_discord_task(interaction.client, updated)  # type: ignore[arg-type]
            await interaction.followup.send(f"Task moved to **{status_map[action]}**.", ephemeral=True)
            return

        if action == "edit":
            if not _v17_can_manage(interaction, task):
                await interaction.response.send_message("Only admins or the task assigner who created this task can edit it.", ephemeral=True)
                return
            from taskbot.modals import TaskEditModal
            await interaction.response.send_modal(TaskEditModal(interaction.client, task))  # type: ignore[arg-type]
            return


class TaskV2View(_BaseLayoutView):  # type: ignore[misc, no-redef]
    def __init__(self, task: dict[str, Any], *, include_controls: bool = True) -> None:
        super().__init__(timeout=None)

        if not supports_components_v2():
            return

        container_cls = getattr(discord.ui, "Container")
        separator_cls = getattr(discord.ui, "Separator")
        action_row_cls = getattr(discord.ui, "ActionRow")

        c = container_cls()

        banner = _v17_banner_ref(task)
        if banner:
            added_banner = _v17_add_media_gallery(c, banner)
            if added_banner:
                _add(c, separator_cls(visible=True))
            else:
                _add(c, _new_text_display("-# Banner could not render as MediaGallery in this discord.py build."))

        title = _clip(task.get("title") or "Untitled Task", 180)
        description = _clip(task.get("description") or "No description provided.", 1800)
        _add(c, _new_text_display(f"# {title}\n\n{description}"))
        _add(c, separator_cls(visible=True))

        claimers = [int(x) for x in _claimers(task)]
        cap = _capacity(task)
        assignees = "\n".join(_mention(x) for x in claimers) if claimers else "No one has claimed this yet."

        # Public V2 text does not provide true arbitrary table columns.
        # This stable horizontal row is the closest V2-native column strip.
        summary_buttons = action_row_cls()
        summary_buttons.add_item(discord.ui.Button(label=f"Status: {_v17_status_label(task)}", style=discord.ButtonStyle.secondary, disabled=True))
        summary_buttons.add_item(discord.ui.Button(label=f"Priority: {_priority(task)}", style=discord.ButtonStyle.secondary, disabled=True))
        summary_buttons.add_item(discord.ui.Button(label=f"Assignees: {len(claimers)}/{cap}", style=discord.ButtonStyle.secondary, disabled=True))
        _add(c, summary_buttons)

        _add(c, _new_text_display(
            f"**Status**\n{_v17_status_markdown(task)}\n"
            f"**Assignees ({len(claimers)}/{cap})**\n{assignees}"
        ))

        _add(c, separator_cls(visible=True))

        _add(c, _new_text_display(
            f"**Authors**\n{_authors(task)}\n\n"
            f"**Roles**\n{_v17_role_line(task)}\n\n"
            f"**OS**\n{_os(task)}\n\n"
            f"**Engine**\n{_engine(task)}\n\n"
            f"**Due Date**\n{_v17_due(task)}"
        ))

        gallery_urls = [u for u in _csv(task.get("gallery_urls") or task.get("image_urls") or task.get("attachment_urls")) if _v17_remote_url(u)]
        if gallery_urls and hasattr(discord.ui, "MediaGallery"):
            for url in gallery_urls[:10]:
                try:
                    _add(c, separator_cls(visible=True))
                    _v17_add_media_gallery(c, url)
                except Exception:
                    pass

        if include_controls:
            archived = _v17_archived(task)
            full = len(claimers) >= cap
            status = _clean_str(task.get("status"), "To Do").lower()

            _add(c, separator_cls(visible=True))
            _add(c, _new_text_display("-# Change status"))

            row1 = action_row_cls()
            for action, label, selected in (
                ("todo", "To Do", status in {"to do", "todo"} and not archived),
                ("progress", "In Progress", status == "in progress" and not archived),
                ("review", "Review", status == "review" and not archived),
                ("done", "Done", status == "done" and not archived),
            ):
                row1.add_item(_V17TaskButton(
                    task,
                    action,
                    label,
                    discord.ButtonStyle.primary if selected else discord.ButtonStyle.secondary,
                    disabled=archived,
                ))
            _add(c, row1)

            _add(c, _new_text_display("-# Claim, edit, or archive this post"))

            row2 = action_row_cls()
            row2.add_item(_V17TaskButton(task, "claim", "Claim", discord.ButtonStyle.primary, disabled=archived or full))
            row2.add_item(_V17TaskButton(task, "unclaim", "Unclaim", discord.ButtonStyle.danger, disabled=archived or not bool(claimers)))
            row2.add_item(_V17TaskButton(task, "edit", "Edit Post", discord.ButtonStyle.secondary, disabled=archived))
            row2.add_item(_V17TaskButton(
                task,
                "unarchive" if archived else "archive",
                "Unarchive" if archived else "Archive",
                discord.ButtonStyle.secondary,
                disabled=False,
            ))
            _add(c, row2)

        self.add_item(c)


def task_message_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    kwargs: dict[str, Any] = {
        "view": TaskV2View(task, include_controls=include_controls),
    }
    banner_file = _v17_banner_file(task)
    if banner_file is not None:
        kwargs["file"] = banner_file
    return kwargs


def task_edit_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    kwargs: dict[str, Any] = {
        "content": None,
        "embed": None,
        "view": TaskV2View(task, include_controls=include_controls),
    }
    banner_file = _v17_banner_file(task)
    if banner_file is not None:
        kwargs["attachments"] = [banner_file]
    return kwargs

# ---- end v17 banner media + claim guard + summary columns ----

# ---- v19 section summary row no markdown table ----

def _v19_status_plain(task: dict[str, Any]) -> str:
    if "_v17_status_label" in globals():
        status = _v17_status_label(task)
    else:
        status = _clean_str(task.get("status"), "To Do")

    low = status.lower()
    if low == "archived":
        return "Archived"
    if low in {"to do", "todo"}:
        return "🟢 To Do"
    if low == "in progress":
        return "🟡 In Progress"
    if low == "review":
        return "💗 Review"
    if low == "done":
        return "✅ Done"
    return status


def _v19_priority_plain(task: dict[str, Any]) -> str:
    priority = _clean_str(task.get("priority"), "Medium")
    low = priority.lower()
    if low == "high":
        return "🔴 High"
    if low == "medium":
        return "🟡 Medium"
    if low == "low":
        return "🟢 Low"
    return priority


def _v19_summary_section(task: dict[str, Any]) -> Any | None:
    # Attempt a Components V2 Section-based inline summary.
    #
    # Discord V2 does not expose a true grid/column primitive. Some discord.py
    # builds render multiple TextDisplay children in a Section compactly; others
    # still stack them vertically. If the local build cannot construct a Section,
    # the task card falls back to disabled button chips.
    if not hasattr(discord.ui, "Section"):
        return None

    claimers = [int(x) for x in _claimers(task)]
    cap = _capacity(task)

    texts = [
        _new_text_display(f"**Status**\n{_v19_status_plain(task)}"),
        _new_text_display(f"**Priority**\n{_v19_priority_plain(task)}"),
        _new_text_display(f"**Assignees**\n{len(claimers)}/{cap} claimed"),
    ]

    section_cls = getattr(discord.ui, "Section")

    try:
        return section_cls(*texts)
    except TypeError:
        try:
            section = section_cls()
            for item in texts:
                section.add_item(item)
            return section
        except Exception:
            return None
    except Exception:
        return None


def _v19_add_summary(container: Any, task: dict[str, Any], action_row_cls: Any) -> None:
    section = _v19_summary_section(task)
    if section is not None:
        _add(container, section)
        return

    # Fallback: this is the only reliable horizontal primitive available through
    # public message components without using legacy embeds.
    claimers = [int(x) for x in _claimers(task)]
    cap = _capacity(task)
    row = action_row_cls()
    row.add_item(discord.ui.Button(label=f"Status: {_v19_status_plain(task)}", style=discord.ButtonStyle.secondary, disabled=True))
    row.add_item(discord.ui.Button(label=f"Priority: {_v19_priority_plain(task)}", style=discord.ButtonStyle.secondary, disabled=True))
    row.add_item(discord.ui.Button(label=f"Assignees: {len(claimers)}/{cap}", style=discord.ButtonStyle.secondary, disabled=True))
    _add(container, row)


def _v19_assignee_details(task: dict[str, Any]) -> str:
    claimers = [int(x) for x in _claimers(task)]
    cap = _capacity(task)
    if not claimers:
        return f"**Assignees ({len(claimers)}/{cap})**\nNo one has claimed this yet."
    lines = "\n".join(f"- {_mention(x)}" for x in claimers)
    return f"**Assignees ({len(claimers)}/{cap})**\n{lines}"


class TaskV2View(_BaseLayoutView):  # type: ignore[misc, no-redef]
    def __init__(self, task: dict[str, Any], *, include_controls: bool = True) -> None:
        super().__init__(timeout=None)

        if not supports_components_v2():
            return

        container_cls = getattr(discord.ui, "Container")
        separator_cls = getattr(discord.ui, "Separator")
        action_row_cls = getattr(discord.ui, "ActionRow")

        c = container_cls()

        banner = _v17_banner_ref(task) if "_v17_banner_ref" in globals() else ""
        if banner:
            added_banner = _v17_add_media_gallery(c, banner) if "_v17_add_media_gallery" in globals() else False
            if added_banner:
                _add(c, separator_cls(visible=True))
            else:
                _add(c, _new_text_display("-# Banner could not render as MediaGallery in this discord.py build."))

        title = _clip(task.get("title") or "Untitled Task", 180)
        description = _clip(task.get("description") or "No description provided.", 1800)
        _add(c, _new_text_display(f"# {title}\n\n{description}"))
        _add(c, separator_cls(visible=True))

        # No markdown table. Try Section first, then fall back to button-chip row.
        _v19_add_summary(c, task, action_row_cls)

        # Keep clickable assignee mentions outside the compact summary.
        _add(c, _new_text_display(_v19_assignee_details(task)))

        _add(c, separator_cls(visible=True))

        role_line_func = _v17_role_line if "_v17_role_line" in globals() else (lambda t: ", ".join(_csv(t.get("job_role") or t.get("job_roles"))) or "Any")
        due_func = _v17_due if "_v17_due" in globals() else (lambda t: _clean_str(t.get("due_date"), "No due date"))

        _add(c, _new_text_display(
            f"**Authors**\n{_authors(task)}\n\n"
            f"**Roles**\n{role_line_func(task)}\n\n"
            f"**OS**\n{_os(task)}\n\n"
            f"**Engine**\n{_engine(task)}\n\n"
            f"**Due Date**\n{due_func(task)}"
        ))

        gallery_urls = [u for u in _csv(task.get("gallery_urls") or task.get("image_urls") or task.get("attachment_urls")) if u.startswith(("http://", "https://"))]
        if gallery_urls and hasattr(discord.ui, "MediaGallery") and "_v17_add_media_gallery" in globals():
            for url in gallery_urls[:10]:
                try:
                    _add(c, separator_cls(visible=True))
                    _v17_add_media_gallery(c, url)
                except Exception:
                    pass

        if include_controls:
            archived = _v17_archived(task) if "_v17_archived" in globals() else bool(task.get("archived"))
            claimers = [int(x) for x in _claimers(task)]
            cap = _capacity(task)
            full = len(claimers) >= cap
            status = _clean_str(task.get("status"), "To Do").lower()

            _add(c, separator_cls(visible=True))
            _add(c, _new_text_display("-# Change status"))

            row1 = action_row_cls()
            for action, label, selected in (
                ("todo", "To Do", status in {"to do", "todo"} and not archived),
                ("progress", "In Progress", status == "in progress" and not archived),
                ("review", "Review", status == "review" and not archived),
                ("done", "Done", status == "done" and not archived),
            ):
                row1.add_item(_V17TaskButton(
                    task,
                    action,
                    label,
                    discord.ButtonStyle.primary if selected else discord.ButtonStyle.secondary,
                    disabled=archived,
                ))
            _add(c, row1)

            _add(c, _new_text_display("-# Claim, edit, or archive this post"))

            row2 = action_row_cls()
            row2.add_item(_V17TaskButton(task, "claim", "Claim", discord.ButtonStyle.primary, disabled=archived or full))
            row2.add_item(_V17TaskButton(task, "unclaim", "Unclaim", discord.ButtonStyle.danger, disabled=archived or not bool(claimers)))
            row2.add_item(_V17TaskButton(task, "edit", "Edit Post", discord.ButtonStyle.secondary, disabled=archived))
            row2.add_item(_V17TaskButton(
                task,
                "unarchive" if archived else "archive",
                "Unarchive" if archived else "Archive",
                discord.ButtonStyle.secondary,
                disabled=False,
            ))
            _add(c, row2)

        self.add_item(c)


def task_message_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    kwargs: dict[str, Any] = {
        "view": TaskV2View(task, include_controls=include_controls),
    }
    banner_file = _v17_banner_file(task) if "_v17_banner_file" in globals() else None
    if banner_file is not None:
        kwargs["file"] = banner_file
    return kwargs


def task_edit_kwargs(task: dict[str, Any], *, include_controls: bool = True) -> dict[str, Any]:  # type: ignore[no-redef]
    kwargs: dict[str, Any] = {
        "content": None,
        "embed": None,
        "view": TaskV2View(task, include_controls=include_controls),
    }
    banner_file = _v17_banner_file(task) if "_v17_banner_file" in globals() else None
    if banner_file is not None:
        kwargs["attachments"] = [banner_file]
    return kwargs

# ---- end v19 section summary row no markdown table ----

