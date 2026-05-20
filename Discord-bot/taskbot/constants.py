from __future__ import annotations

import discord

STATUS_CHOICES = ["To Do", "In Progress", "Review", "Done", "Archived"]
ACTIVE_STATUSES = ["To Do", "In Progress", "Review"]
PRIORITY_CHOICES = ["Low", "Medium", "High", "Urgent"]

JOB_ROLES = [
    "Programmer",
    "2D Artist",
    "UI Artist",
    "Writer",
    "SFX",
    "VFX",
    "Music Composer",
    "3D Artist",
    "3D Modeler",
    "Rigging",
    "3D Animator",
    "2D Animator",
    "Playtester",
]

JOB_ROLE_EMOJIS = {
    "Programmer": "💻",
    "2D Artist": "🎨",
    "UI Artist": "🧩",
    "Writer": "✍️",
    "SFX": "🔊",
    "VFX": "✨",
    "Music Composer": "🎵",
    "3D Artist": "🧊",
    "3D Modeler": "🛠️",
    "Rigging": "🦴",
    "3D Animator": "🎬",
    "2D Animator": "📽️",
    "Playtester": "🎮",
}

DEV_ENVIRONMENTS = ["Windows", "Mac", "Linux"]
GAME_ENGINES = ["Unity", "Unreal", "Godot", "Other"]
TASK_TYPES = ["Bug Fix", "Feature", "Code", "Art", "2D", "3D", "UI", "Research", "Writing", "Sound"]
GAME_PROGRAMS = [
    "Unity",
    "Unreal",
    "Godot",
    "Blender",
    "Maya",
    "Aseprite",
    "Photoshop",
    "Illustrator",
    "Figma",
    "FMOD",
    "Wwise",
    "Reaper",
    "Audacity",
    "GitHub",
]
POSITIONS_NEEDED_CHOICES = [1, 2, 3, 4, 5, 6, 7, 8]

STATUS_COLORS = {
    "To Do": discord.Color.light_grey(),
    "In Progress": discord.Color.blurple(),
    "Review": discord.Color.gold(),
    "Done": discord.Color.green(),
    "Archived": discord.Color.dark_grey(),
}
