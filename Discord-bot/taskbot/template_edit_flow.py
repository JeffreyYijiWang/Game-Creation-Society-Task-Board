from __future__ import annotations

from dataclasses import dataclass, field

import discord

from taskbot.constants import DEV_ENVIRONMENTS, GAME_ENGINES, JOB_ROLES, POSITIONS_NEEDED_CHOICES

try:
    from taskbot.constants import TASK_TYPES
except Exception:
    TASK_TYPES = ["Bug Fix", "Feature", "Code", "Art", "2D", "3D", "UI", "Research", "Writing", "Sound"]


def _csv_list(value: object, fallback: list[str]) -> list[str]:
    if value is None:
        return list(fallback)
    if isinstance(value, list):
        parts = [str(x).strip() for x in value if str(x).strip()]
    else:
        parts = [x.strip() for x in str(value).split(",") if x.strip()]
    return parts or list(fallback)


@dataclass
class TemplateEditState:
    positions_needed: int = 1
    job_roles: list[str] = field(default_factory=lambda: ["Programmer"])
    dev_environments: list[str] = field(default_factory=lambda: ["Windows"])
    game_engine: str = "Unity"
    task_types: list[str] = field(default_factory=lambda: ["Feature"])
    thumbnail_url: str = ""
    custom_game_engine: str = ""
    game_programs: str = ""


def state_from_template(template: dict, *, thumbnail_url: str = "", custom_game_engine: str = "") -> TemplateEditState:
    return TemplateEditState(
        positions_needed=max(1, int(template.get("positions_needed") or 1)),
        job_roles=_csv_list(template.get("job_role"), ["Programmer"]),
        dev_environments=_csv_list(template.get("dev_environment"), ["Windows"]),
        game_engine=str(template.get("game_engine") or "Unity"),
        task_types=_csv_list(template.get("task_type") or template.get("task_types"), ["Feature"]),
        thumbnail_url=thumbnail_url or str(template.get("thumbnail_url") or ""),
        custom_game_engine=custom_game_engine or str(template.get("custom_game_engine") or ""),
        game_programs=str(template.get("game_programs") or ""),
    )


def template_edit_setup_embed(template: dict, state: TemplateEditState | None = None, *, page: int = 1) -> discord.Embed:
    state = state or state_from_template(template)
    embed = discord.Embed(
        title=f"Edit Template — {template.get('name', 'template')} — Step {page}/2",
        description=(
            "This uses the same guided dropdown process as task creation, but the final form "
            "saves back into the template instead of posting a new task."
        ),
        color=discord.Color.gold(),
    )
    if page == 1:
        embed.add_field(name="Job roles", value="Choose one or more roles this template usually needs.", inline=False)
        embed.add_field(name="People needed", value="Choose the default claim capacity for tasks made from this template.", inline=False)
        embed.add_field(name="Development environments", value="Choose all supported platforms.", inline=False)
        embed.add_field(name="Task type", value="Choose broad search/filter tags.", inline=False)
    else:
        embed.add_field(name="Game engine / program", value="Choose the main engine. Use `Other` plus the custom engine field if needed.", inline=False)
        embed.add_field(name="Final template form", value="Press **Continue to Template Form** to edit title, description, priority, due date, links, programs/tools, and custom tags.", inline=False)

    embed.add_field(
        name="Current selections",
        value=(
            f"**Roles:** {', '.join(state.job_roles)}\n"
            f"**People needed:** {state.positions_needed}\n"
            f"**Environments:** {', '.join(state.dev_environments)}\n"
            f"**Task types:** {', '.join(state.task_types)}\n"
            f"**Engine:** {state.game_engine}"
            + (f" / {state.custom_game_engine}" if state.custom_game_engine else "")
        ),
        inline=False,
    )
    return embed


class _TemplateStateSelect(discord.ui.Select):
    async def refresh(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, TemplateEditStepOneView):
            await interaction.response.edit_message(embed=template_edit_setup_embed(view.template, view.state, page=1), view=view)
            return
        if isinstance(view, TemplateEditStepTwoView):
            await interaction.response.edit_message(embed=template_edit_setup_embed(view.template, view.state, page=2), view=view)
            return
        await interaction.response.send_message("This template editor is no longer valid.", ephemeral=True)


class TemplateJobRoleSelect(_TemplateStateSelect):
    def __init__(self, state: TemplateEditState) -> None:
        super().__init__(
            placeholder="1) Job roles",
            min_values=1,
            max_values=min(5, len(JOB_ROLES)),
            options=[discord.SelectOption(label=x, value=x, default=x in state.job_roles) for x in JOB_ROLES[:25]],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, TemplateEditStepOneView)
        view.state.job_roles = list(self.values)
        await self.refresh(interaction)


class TemplatePositionsSelect(_TemplateStateSelect):
    def __init__(self, state: TemplateEditState) -> None:
        super().__init__(
            placeholder="2) People needed",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=str(n), value=str(n), default=n == state.positions_needed)
                for n in POSITIONS_NEEDED_CHOICES[:25]
            ],
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, TemplateEditStepOneView)
        view.state.positions_needed = int(self.values[0])
        await self.refresh(interaction)


class TemplateDevEnvironmentSelect(_TemplateStateSelect):
    def __init__(self, state: TemplateEditState) -> None:
        super().__init__(
            placeholder="3) Development environments",
            min_values=1,
            max_values=len(DEV_ENVIRONMENTS),
            options=[discord.SelectOption(label=x, value=x, default=x in state.dev_environments) for x in DEV_ENVIRONMENTS],
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, TemplateEditStepOneView)
        view.state.dev_environments = list(self.values)
        await self.refresh(interaction)


class TemplateTaskTypeSelect(_TemplateStateSelect):
    def __init__(self, state: TemplateEditState) -> None:
        super().__init__(
            placeholder="4) Task type",
            min_values=1,
            max_values=min(5, len(TASK_TYPES)),
            options=[discord.SelectOption(label=x, value=x, default=x in state.task_types) for x in TASK_TYPES[:25]],
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, TemplateEditStepOneView)
        view.state.task_types = list(self.values)
        await self.refresh(interaction)


class TemplateGameEngineSelect(_TemplateStateSelect):
    def __init__(self, state: TemplateEditState) -> None:
        super().__init__(
            placeholder="5) Game engine / program",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=x, value=x, default=x == state.game_engine) for x in GAME_ENGINES[:25]],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, TemplateEditStepTwoView)
        view.state.game_engine = self.values[0]
        await self.refresh(interaction)


class TemplateEditStepOneView(discord.ui.View):
    def __init__(
        self,
        template: dict,
        owner_id: int,
        *,
        thumbnail_url: str = "",
        custom_game_engine: str = "",
        state: TemplateEditState | None = None,
        timeout: float | None = 600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.template = template
        self.owner_id = owner_id
        self.state = state or state_from_template(template, thumbnail_url=thumbnail_url, custom_game_engine=custom_game_engine)
        self.add_item(TemplateJobRoleSelect(self.state))
        self.add_item(TemplatePositionsSelect(self.state))
        self.add_item(TemplateDevEnvironmentSelect(self.state))
        self.add_item(TemplateTaskTypeSelect(self.state))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the template owner can edit this template.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Next: Engine / Tools", style=discord.ButtonStyle.primary, row=4)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=template_edit_setup_embed(self.template, self.state, page=2),
            view=TemplateEditStepTwoView(self.template, self.owner_id, state=self.state),
        )


class TemplateEditStepTwoView(discord.ui.View):
    def __init__(
        self,
        template: dict,
        owner_id: int,
        *,
        state: TemplateEditState,
        timeout: float | None = 600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.template = template
        self.owner_id = owner_id
        self.state = state
        self.add_item(TemplateGameEngineSelect(self.state))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the template owner can edit this template.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=4)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=template_edit_setup_embed(self.template, self.state, page=1),
            view=TemplateEditStepOneView(self.template, self.owner_id, state=self.state),
        )

    @discord.ui.button(label="Continue to Template Form", style=discord.ButtonStyle.success, row=4)
    async def continue_to_form(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from taskbot.modals import TemplateSaveModal

        kwargs = dict(
            guild_id=int(self.template["guild_id"]),
            owner_id=int(self.template["owner_id"]),
            name=str(self.template["name"]),
            thumbnail_url=self.state.thumbnail_url,
            positions_needed=self.state.positions_needed,
            job_role=", ".join(self.state.job_roles),
            dev_environment=", ".join(self.state.dev_environments),
            game_engine=self.state.game_engine,
            custom_game_engine=self.state.custom_game_engine,
            game_programs=self.state.game_programs,
            existing=self.template,
        )

        task_type_value = ", ".join(self.state.task_types)
        try:
            modal = TemplateSaveModal(**kwargs, task_type=task_type_value)
        except TypeError:
            modal = TemplateSaveModal(**kwargs, task_types=task_type_value)

        await interaction.response.send_modal(modal)
