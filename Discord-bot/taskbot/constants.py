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


OS_OPTIONS = DEV_ENVIRONMENTS

JOB_ROLE_MENTION_IDS = {
    "Programmer": 1506827182889111552,
    "Writer": 1506828823851700415,
    "VFX": 1506828829862400131,
    "3D Animator": 1506828834723467274,
    "Playtester": 1506828836250325222,
    "Music Composer": 1506828831560958143,
    "2D Artist": 1506828571467841586,
    "2D Animator": 1506828835402813571,
    "Rigging": 1506828833725218907,
    "3D Artist": 1506828832269668362,
    "3D Modeler": 1506828832756207759,
    "UI Artist": 1506828836963221646,
    "SFX": 1506828829862400131,
}
