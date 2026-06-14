"""Centralised settings for York."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Emoji:
    ok: str = os.getenv("YORK_EMOJI_OK", "◆")
    warn: str = os.getenv("YORK_EMOJI_WARN", "◈")
    error: str = os.getenv("YORK_EMOJI_ERROR", "✖")
    info: str = os.getenv("YORK_EMOJI_INFO", "❖")
    spark: str = os.getenv("YORK_EMOJI_SPARK", "✦")
    hammer: str = os.getenv("YORK_EMOJI_HAMMER", "⚒")
    shield: str = os.getenv("YORK_EMOJI_SHIELD", "❘❘")
    boot: str = os.getenv("YORK_EMOJI_BOOT", "▶")
    mute: str = os.getenv("YORK_EMOJI_MUTE", "◑")
    member: str = os.getenv("YORK_EMOJI_MEMBER", "◉")
    role: str = os.getenv("YORK_EMOJI_ROLE", "◐")
    crown: str = os.getenv("YORK_EMOJI_CROWN", "♛")
    brain: str = os.getenv("YORK_EMOJI_BRAIN", "✺")
    wave: str = os.getenv("YORK_EMOJI_WAVE", "～")
    fish: str = os.getenv("YORK_EMOJI_FISH", "🎣")
    crate: str = os.getenv("YORK_EMOJI_CRATE", "📦")


@dataclass(frozen=True)
class Settings:
    discord_token: str = field(default_factory=lambda: os.getenv("DISCORD_BOT_TOKEN", ""))
    openai_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    proxy_key: str = field(default_factory=lambda: os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY", ""))
    proxy_base_url: str = field(default_factory=lambda: os.getenv("AI_INTEGRATIONS_OPENAI_BASE_URL", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("YORK_MODEL", "gpt-5-nano"))

    bot_name: str = "York"
    creator: str = "Berry"

    # Path where profiles.json / warnings.json / memory.json are stored.
    # Set DATA_DIR=/data on Katabump (or any host) to a volume that persists
    # across deploys so player data is never wiped.
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "bot/data")))

    wake_phrases: tuple[str, ...] = ("hey york", "hi york", "yo york", "york,", "york!")
    detach_phrases: tuple[str, ...] = (
        "enough", "done", "set free", "detach", "goodbye", "bye york", "stand down",
    )

    accent_color: int = 0x6E5BFF
    success_color: int = 0x4ADE80
    warn_color: int = 0xFACC15
    danger_color: int = 0xF87171

    proactive_min_minutes: int = 35
    proactive_max_minutes: int = 95

    history_limit: int = 12

    emoji: Emoji = field(default_factory=Emoji)


settings = Settings()
