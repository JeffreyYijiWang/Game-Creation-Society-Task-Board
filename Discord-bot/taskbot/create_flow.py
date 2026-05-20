from __future__ import annotations

from dataclasses import dataclass, field

import discord
from discord.ext import commands

from taskbot.constants import JOB_ROLES, DEV_ENVIRONMENTS, GAME_ENGINES, POSITIONS_NEEDED_CHOICES


TASK_TYPES = [
    "Bug Fix",
    "Feature",
    "Code",
    "Art",
    "2D",
    "3D",
    "UI",
    "Research",
    "Writing",
    "Sound",
]


@dataclass
class CreateTaskState:
    positions_needed: int = 1
    job_roles: list[str] = field(default_factory=lambda: ["Programmer"])
    dev_environments: list[str] = field(default_factory=lambda: ["Windows"])
    game_engine: str = "Unity"
    task_types: list[str] = field(default_factory=lambda: ["Feature"])
    thumbnail_url: str = ""
    custom_game_engine: str = ""


def create_setup_embed(state: CreateTaskState | None = None, *, page: int = 1) -> discord.Embed:
    state = state or CreateTaskState()
    embed = discord.Embed(
        title=f"Create Task — Setup {page}/2",
        description=(
            "Choose the structured fields below. Discord only allows 5 component rows per message, "
            "so the create setup is split into two pages."
        ),
        color=discord.Color.blurple(),
    )

    if page == 1:
        embed.add_field(
            name="1. Job description / role",
            value="Choose one or more roles this task needs, such as Programmer, 2D Artist, Writer, or Playtester.",
            inline=False,
        )
        embed.add_field(
            name="2. People needed",
            value="How many people can claim this post before it is considered filled.",
            inline=False,
        )
        embed.add_field(
            name="3. Development environment",
            value="Choose all supported platforms. This is multi-select: Windows, Mac, Linux.",
            inline=False,
        )
        embed.add_field(
            name="4. Game engine / program familiarity",
            value="Choose Unity, Unreal, Godot, or Other. If Other, use the optional `custom_game_engine` slash-command field.",
            inline=False,
        )
    else:
        embed.add_field(
            name="5. Task type",
            value="Choose one or more broad tags such as Bug Fix, Feature, Art, UI, Research, Writing, or Sound.",
            inline=False,
        )
        embed.add_field(
            name="Next form",
            value=(
                "After this, press **Continue to Form**. The form is for title, description, due date, "
                "links, and extra tags. Separate multiple tags or links with commas or new lines."
            ),
            inline=False,
        )

    embed.add_field(
        name="Current selections",
        value=(
            f"**Roles:** {', '.join(state.job_roles)}\n"
            f"**People needed:** {state.positions_needed}\n"
            f"**Environments:** {', '.join(state.dev_environments)}\n"
            f"**Engine/program:** {state.game_engine}"
            + (f" / {state.custom_game_engine}" if state.custom_game_engine else "")
            + f"\n**Task types:** {', '.join(state.task_types)}"
        ),
        inline=False,
    )
    return embed


class _StateSelect(discord.ui.Select):
    async def refresh(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, TaskCreateSetupView):
            await interaction.response.edit_message(embed=create_setup_embed(view.state, page=1), view=view)
            return
        if isinstance(view, TaskCreateTypeView):
            await interaction.response.edit_message(embed=create_setup_embed(view.state, page=2), view=view)
            return
        await interaction.response.send_message("This setup view is no longer valid.", ephemeral=True)


class JobRoleSelect(_StateSelect):
    def __init__(self, state: CreateTaskState) -> None:
        super().__init__(
            placeholder="Job description / role needed",
            min_values=1,
            max_values=min(5, len(JOB_ROLES)),
            options=[
                discord.SelectOption(label=x, value=x, default=x in state.job_roles)
                for x in JOB_ROLES[:25]
            ],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, TaskCreateSetupView)
        view.state.job_roles = list(self.values)
        await self.refresh(interaction)


class PositionsNeededSelect(_StateSelect):
    def __init__(self, state: CreateTaskState) -> None:
        super().__init__(
            placeholder="Number of people needed",
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
        assert isinstance(view, TaskCreateSetupView)
        view.state.positions_needed = int(self.values[0])
        await self.refresh(interaction)


class DevEnvironmentSelect(_StateSelect):
    def __init__(self, state: CreateTaskState) -> None:
        super().__init__(
            placeholder="Development environment / supported OS",
            min_values=1,
            max_values=len(DEV_ENVIRONMENTS),
            options=[
                discord.SelectOption(label=x, value=x, default=x in state.dev_environments)
                for x in DEV_ENVIRONMENTS
            ],
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, TaskCreateSetupView)
        view.state.dev_environments = list(self.values)
        await self.refresh(interaction)


class GameEngineSelect(_StateSelect):
    def __init__(self, state: CreateTaskState) -> None:
        super().__init__(
            placeholder="Game engine / program familiarity",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=x, value=x, default=x == state.game_engine)
                for x in GAME_ENGINES[:25]
            ],
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, TaskCreateSetupView)
        view.state.game_engine = self.values[0]
        await self.refresh(interaction)


class TaskTypeSelect(_StateSelect):
    def __init__(self, state: CreateTaskState) -> None:
        super().__init__(
            placeholder="Task type / major tag",
            min_values=1,
            max_values=min(5, len(TASK_TYPES)),
            options=[
                discord.SelectOption(label=x, value=x, default=x in state.task_types)
                for x in TASK_TYPES
            ],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, TaskCreateTypeView)
        view.state.task_types = list(self.values)
        await self.refresh(interaction)


class TaskCreateSetupView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        owner_id: int,
        *,
        thumbnail_url: str = "",
        custom_game_engine: str = "",
        state: CreateTaskState | None = None,
        timeout: float | None = 600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.owner_id = owner_id
        self.state = state or CreateTaskState(
            thumbnail_url=thumbnail_url,
            custom_game_engine=custom_game_engine,
        )
        self.add_item(JobRoleSelect(self.state))
        self.add_item(PositionsNeededSelect(self.state))
        self.add_item(DevEnvironmentSelect(self.state))
        self.add_item(GameEngineSelect(self.state))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person creating this task can use this setup panel.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Next: Task Type", style=discord.ButtonStyle.primary, row=4)
    async def next_to_task_type(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=create_setup_embed(self.state, page=2),
            view=TaskCreateTypeView(
                self.bot,
                self.owner_id,
                state=self.state,
            ),
        )


class TaskCreateTypeView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        owner_id: int,
        *,
        state: CreateTaskState,
        timeout: float | None = 600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.owner_id = owner_id
        self.state = state
        self.add_item(TaskTypeSelect(self.state))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person creating this task can use this setup panel.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=4)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=create_setup_embed(self.state, page=1),
            view=TaskCreateSetupView(
                self.bot,
                self.owner_id,
                state=self.state,
            ),
        )

    @discord.ui.button(label="Continue to Form", style=discord.ButtonStyle.success, row=4)
    async def continue_to_form(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from taskbot.modals import TaskCreateModal

        try:
            await interaction.response.send_modal(
                TaskCreateModal(
                    self.bot,
                    thumbnail_url=self.state.thumbnail_url,
                    positions_needed=self.state.positions_needed,
                    job_role=", ".join(self.state.job_roles),
                    dev_environment=", ".join(self.state.dev_environments),
                    game_engine=self.state.game_engine,
                    custom_game_engine=self.state.custom_game_engine,
                    task_types=", ".join(self.state.task_types),
                )
            )
        except Exception as exc:
            import traceback

            traceback.print_exception(type(exc), exc, exc.__traceback__)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Task create form could not open. Check the bot terminal for the traceback.",
                    ephemeral=True,
                )
