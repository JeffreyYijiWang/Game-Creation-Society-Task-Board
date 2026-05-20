from __future__ import annotations

from pathlib import Path
import re
import shutil

ROOT = Path.cwd()
BACKUP_SUFFIX = ".bak_v6_repair"

CREATE_FLOW_CONTENT = 'from __future__ import annotations\n\nfrom dataclasses import dataclass, field\n\nimport discord\nfrom discord.ext import commands\n\nfrom taskbot.constants import JOB_ROLES, DEV_ENVIRONMENTS, GAME_ENGINES, POSITIONS_NEEDED_CHOICES\n\n\nTASK_TYPES = [\n    "Bug Fix",\n    "Feature",\n    "Code",\n    "Art",\n    "2D",\n    "3D",\n    "UI",\n    "Research",\n    "Writing",\n    "Sound",\n]\n\n\n@dataclass\nclass CreateTaskState:\n    positions_needed: int = 1\n    job_roles: list[str] = field(default_factory=lambda: ["Programmer"])\n    dev_environments: list[str] = field(default_factory=lambda: ["Windows"])\n    game_engine: str = "Unity"\n    task_types: list[str] = field(default_factory=lambda: ["Feature"])\n    thumbnail_url: str = ""\n    custom_game_engine: str = ""\n\n\ndef create_setup_embed(state: CreateTaskState | None = None) -> discord.Embed:\n    state = state or CreateTaskState()\n    embed = discord.Embed(\n        title="Create Task — Setup",\n        description=(\n            "Choose the structured fields below, then press **Continue to Form**. "\n            "The next form is for long text: title, description, due date, links, and extra tags."\n        ),\n        color=discord.Color.blurple(),\n    )\n    embed.add_field(\n        name="1. Job description / role",\n        value="Choose one or more roles this task needs, such as Programmer, 2D Artist, Writer, or Playtester.",\n        inline=False,\n    )\n    embed.add_field(\n        name="2. People needed",\n        value="How many people can claim this post before it is considered filled.",\n        inline=False,\n    )\n    embed.add_field(\n        name="3. Development environment",\n        value="Choose all supported platforms. This is multi-select: Windows, Mac, Linux.",\n        inline=False,\n    )\n    embed.add_field(\n        name="4. Game engine / program familiarity",\n        value="Choose Unity, Unreal, Godot, or Other. If Other, use the optional `custom_game_engine` slash-command field.",\n        inline=False,\n    )\n    embed.add_field(\n        name="5. Task type",\n        value="Choose one or more broad tags such as Bug Fix, Feature, Art, UI, Research, Writing, or Sound.",\n        inline=False,\n    )\n    embed.add_field(\n        name="Current selections",\n        value=(\n            f"**Roles:** {\', \'.join(state.job_roles)}\\n"\n            f"**People needed:** {state.positions_needed}\\n"\n            f"**Environments:** {\', \'.join(state.dev_environments)}\\n"\n            f"**Engine/program:** {state.game_engine}"\n            + (f" / {state.custom_game_engine}" if state.custom_game_engine else "")\n            + f"\\n**Task types:** {\', \'.join(state.task_types)}"\n        ),\n        inline=False,\n    )\n    return embed\n\n\nclass _StateSelect(discord.ui.Select):\n    async def refresh(self, interaction: discord.Interaction) -> None:\n        view = self.view\n        assert isinstance(view, TaskCreateSetupView)\n        await interaction.response.edit_message(embed=create_setup_embed(view.state), view=view)\n\n\nclass JobRoleSelect(_StateSelect):\n    def __init__(self) -> None:\n        super().__init__(\n            placeholder="Job description / role needed",\n            min_values=1,\n            max_values=min(5, len(JOB_ROLES)),\n            options=[discord.SelectOption(label=x, value=x) for x in JOB_ROLES[:25]],\n        )\n\n    async def callback(self, interaction: discord.Interaction) -> None:\n        view = self.view\n        assert isinstance(view, TaskCreateSetupView)\n        view.state.job_roles = list(self.values)\n        await self.refresh(interaction)\n\n\nclass PositionsNeededSelect(_StateSelect):\n    def __init__(self) -> None:\n        super().__init__(\n            placeholder="Number of people needed",\n            min_values=1,\n            max_values=1,\n            options=[discord.SelectOption(label=str(n), value=str(n)) for n in POSITIONS_NEEDED_CHOICES[:25]],\n        )\n\n    async def callback(self, interaction: discord.Interaction) -> None:\n        view = self.view\n        assert isinstance(view, TaskCreateSetupView)\n        view.state.positions_needed = int(self.values[0])\n        await self.refresh(interaction)\n\n\nclass DevEnvironmentSelect(_StateSelect):\n    def __init__(self) -> None:\n        super().__init__(\n            placeholder="Development environment / supported OS",\n            min_values=1,\n            max_values=len(DEV_ENVIRONMENTS),\n            options=[discord.SelectOption(label=x, value=x) for x in DEV_ENVIRONMENTS],\n        )\n\n    async def callback(self, interaction: discord.Interaction) -> None:\n        view = self.view\n        assert isinstance(view, TaskCreateSetupView)\n        view.state.dev_environments = list(self.values)\n        await self.refresh(interaction)\n\n\nclass GameEngineSelect(_StateSelect):\n    def __init__(self) -> None:\n        super().__init__(\n            placeholder="Game engine / program familiarity",\n            min_values=1,\n            max_values=1,\n            options=[discord.SelectOption(label=x, value=x) for x in GAME_ENGINES[:25]],\n        )\n\n    async def callback(self, interaction: discord.Interaction) -> None:\n        view = self.view\n        assert isinstance(view, TaskCreateSetupView)\n        view.state.game_engine = self.values[0]\n        await self.refresh(interaction)\n\n\nclass TaskTypeSelect(_StateSelect):\n    def __init__(self) -> None:\n        super().__init__(\n            placeholder="Task type / major tag",\n            min_values=1,\n            max_values=min(5, len(TASK_TYPES)),\n            options=[discord.SelectOption(label=x, value=x) for x in TASK_TYPES],\n        )\n\n    async def callback(self, interaction: discord.Interaction) -> None:\n        view = self.view\n        assert isinstance(view, TaskCreateSetupView)\n        view.state.task_types = list(self.values)\n        await self.refresh(interaction)\n\n\nclass TaskCreateSetupView(discord.ui.View):\n    def __init__(\n        self,\n        bot: commands.Bot,\n        owner_id: int,\n        *,\n        thumbnail_url: str = "",\n        custom_game_engine: str = "",\n        timeout: float | None = 600,\n    ) -> None:\n        super().__init__(timeout=timeout)\n        self.bot = bot\n        self.owner_id = owner_id\n        self.state = CreateTaskState(\n            thumbnail_url=thumbnail_url,\n            custom_game_engine=custom_game_engine,\n        )\n        self.add_item(JobRoleSelect())\n        self.add_item(PositionsNeededSelect())\n        self.add_item(DevEnvironmentSelect())\n        self.add_item(GameEngineSelect())\n        self.add_item(TaskTypeSelect())\n\n    async def interaction_check(self, interaction: discord.Interaction) -> bool:\n        if interaction.user.id != self.owner_id:\n            await interaction.response.send_message("Only the person creating this task can use this setup panel.", ephemeral=True)\n            return False\n        return True\n\n    @discord.ui.button(label="Continue to Form", style=discord.ButtonStyle.success, row=4)\n    async def continue_to_form(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:\n        from taskbot.modals import TaskCreateModal\n\n        await interaction.response.send_modal(\n            TaskCreateModal(\n                self.bot,\n                thumbnail_url=self.state.thumbnail_url,\n                positions_needed=self.state.positions_needed,\n                job_role=", ".join(self.state.job_roles),\n                dev_environment=", ".join(self.state.dev_environments),\n                game_engine=self.state.game_engine,\n                custom_game_engine=self.state.custom_game_engine,\n                task_types=", ".join(self.state.task_types),\n            )\n        )\n'
CREATE_CMD_REPLACEMENT = '@task_group.command(name="create", description="Open the guided task creation dropdown flow")\nasync def task_create(\n    interaction: discord.Interaction,\n    thumbnail: Optional[discord.Attachment] = None,\n    custom_game_engine: Optional[str] = None,\n) -> None:\n    thumbnail_url = thumbnail.url if thumbnail else ""\n    if thumbnail and thumbnail.content_type and not thumbnail.content_type.startswith("image/"):\n        await interaction.response.send_message("The thumbnail must be an image attachment.", ephemeral=True)\n        return\n\n    state = CreateTaskState(thumbnail_url=thumbnail_url, custom_game_engine=custom_game_engine or "")\n    await interaction.response.send_message(\n        embed=create_setup_embed(state),\n        view=TaskCreateSetupView(\n            interaction.client,  # type: ignore[arg-type]\n            interaction.user.id,\n            thumbnail_url=thumbnail_url,\n            custom_game_engine=custom_game_engine or "",\n        ),\n        ephemeral=True,\n    )\n'
NORMALIZER_ADDITION = '\n\n\ndef normalize_dev_environments(envs: str | list[str] | None) -> str:\n    if not envs:\n        return "Windows"\n    if isinstance(envs, str):\n        raw_parts = [part.strip() for part in envs.split(",") if part.strip()]\n    else:\n        raw_parts = [str(part).strip() for part in envs if str(part).strip()]\n\n    valid: list[str] = []\n    seen: set[str] = set()\n    for part in raw_parts:\n        match = normalize_choice(part, DEV_ENVIRONMENTS, "")\n        if match and match not in seen:\n            seen.add(match)\n            valid.append(match)\n    return ", ".join(valid) if valid else "Windows"\n'
SPLIT_ENV_TAGS = '\n\n\ndef split_env_tags(value: str | None) -> list[str]:\n    if not value:\n        return []\n    return [part.strip() for part in str(value).split(",") if part.strip()]\n'

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

def ensure_create_flow() -> None:
    p = ROOT / "taskbot" / "create_flow.py"
    backup(p)
    p.write_text(CREATE_FLOW_CONTENT, encoding="utf-8")
    print("[ok] ensured taskbot/create_flow.py")

def repair_commands() -> None:
    rel = "taskbot/commands.py"
    text = read(rel)

    import_line = "from taskbot.create_flow import TaskCreateSetupView, create_setup_embed, CreateTaskState\n"
    if import_line.strip() not in text:
        anchor = "from taskbot.config import settings\n"
        if anchor in text:
            text = text.replace(anchor, anchor + import_line, 1)
        else:
            text = import_line + text
        print("[ok] added create_flow import to commands.py")

    if "TaskCreateSetupView(" not in text or "create_setup_embed(state)" not in text:
        start = text.find('@task_group.command(name="create"')
        if start == -1:
            print("[warn] could not find /task create command to replace")
        else:
            next_cmd = text.find("\n\n@task_group.command", start + 1)
            if next_cmd == -1:
                print("[warn] could not find end of /task create command")
            else:
                text = text[:start] + CREATE_CMD_REPLACEMENT + text[next_cmd:]
                print("[ok] replaced /task create with setup dropdown flow")

    write(rel, text)

def repair_modals() -> None:
    rel = "taskbot/modals.py"
    text = read(rel)

    if "task_types:" not in text:
        text, n = re.subn(
            r'(\n\s*custom_game_engine:\s*str\s*=\s*["\']["\'],\n)(\s*template:\s*dict\s*\|\s*None\s*=\s*None,)',
            r'\1        task_types: str | list[str] = "",\n\2',
            text,
            count=1,
        )
        if n == 0:
            text, n = re.subn(
                r'(\n\s*template:\s*dict\s*\|\s*None\s*=\s*None,)',
                r'\n        task_types: str | list[str] = "",\1',
                text,
                count=1,
            )
        print("[ok] added task_types parameter" if n else "[warn] could not add task_types parameter")

    if "self.task_types" not in text:
        pattern = r'(\n\s*self\.custom_game_engine\s*=\s*custom_game_engine\s+or\s+\(template\s+or\s+\{\}\)\.get\("custom_game_engine",\s*""\)\n)'
        text, n = re.subn(
            pattern,
            r'\1        if isinstance(task_types, list):\n            self.task_types = ", ".join(task_types)\n        else:\n            self.task_types = task_types or (template or {}).get("task_types", "")\n',
            text,
            count=1,
        )
        print("[ok] added self.task_types assignment" if n else "[warn] could not add self.task_types assignment")

    if "if self.task_types:" not in text:
        old = '        tags, links = self.parse_tags_and_links(str(self.tags_and_links.value))\n'
        new = old + '        if self.task_types:\n            tags = ", ".join(part for part in [self.task_types, tags] if part)\n'
        if old in text:
            text = text.replace(old, new, 1)
            print("[ok] included task types in created task tags")
        else:
            print("[warn] could not find TaskCreateModal tags/links parse line")

    write(rel, text)

def repair_utils() -> None:
    rel = "taskbot/utils.py"
    text = read(rel)
    if "def normalize_dev_environments" not in text:
        marker = 'def normalize_dev_environment(env: str | None) -> str:\n    return normalize_choice(env, DEV_ENVIRONMENTS, "Windows")\n'
        if marker in text:
            text = text.replace(marker, marker + NORMALIZER_ADDITION, 1)
        else:
            text += NORMALIZER_ADDITION
        print("[ok] added normalize_dev_environments")
    write(rel, text)

def repair_db() -> None:
    rel = "taskbot/db.py"
    text = read(rel)

    import_section = text.split("def init_db", 1)[0]
    if "normalize_dev_environments" not in import_section:
        if "normalize_dev_environment," in text:
            text = text.replace("normalize_dev_environment,", "normalize_dev_environment,\n    normalize_dev_environments,", 1)
            print("[ok] added normalize_dev_environments import")
        elif "from taskbot.utils import (" in text:
            text = text.replace("from taskbot.utils import (", "from taskbot.utils import (\n    normalize_dev_environments,", 1)
            print("[ok] added normalize_dev_environments import to utils block")
        else:
            print("[warn] could not locate taskbot.utils import block in db.py")

    if "normalize_dev_environment(dev_environment)" in text:
        text = text.replace("normalize_dev_environment(dev_environment)", "normalize_dev_environments(dev_environment)")
        print("[ok] replaced normalize_dev_environment calls in db.py")

    write(rel, text)

def repair_forum() -> None:
    rel = "taskbot/forum.py"
    text = read(rel)

    if "def split_env_tags" not in text:
        matches = list(re.finditer(r'^(?:from|import)\s+.*$', text, flags=re.MULTILINE))
        if matches:
            pos = matches[-1].end()
            text = text[:pos] + SPLIT_ENV_TAGS + text[pos:]
        else:
            text = SPLIT_ENV_TAGS + text
        print("[ok] added split_env_tags to forum.py")

    replaced = False
    for pat in ['        task.get("dev_environment") or "",\n', "        task.get('dev_environment') or '',\n"]:
        if pat in text:
            text = text.replace(pat, '        *split_env_tags(task.get("dev_environment") or ""),\n', 1)
            replaced = True
            break
    if replaced:
        print("[ok] expanded dev environment forum tags")
    else:
        print("[skip] did not find exact dev_environment tag line; forum tags may still work but may not split multi-env values")

    write(rel, text)

def main() -> None:
    required = ["bot.py", "taskbot/commands.py", "taskbot/modals.py", "taskbot/db.py", "taskbot/utils.py", "taskbot/forum.py"]
    missing = [p for p in required if not (ROOT / p).exists()]
    if missing:
        raise SystemExit(f"Run this from the folder containing bot.py and taskbot/. Missing: {missing}")

    ensure_create_flow()
    repair_commands()
    repair_modals()
    repair_utils()
    repair_db()
    repair_forum()

    print("\nRepair complete. Backups were created with suffix:", BACKUP_SUFFIX)
    print("Now run:")
    print("  python -m compileall -q bot.py taskbot")
    print("Then restart:")
    print("  python .\\bot.py")

if __name__ == "__main__":
    main()
