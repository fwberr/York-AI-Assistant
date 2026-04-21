"""Centralised settings for York."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Emoji:
    """Custom-icon-friendly glyphs.

    Replace any value with `<:name:id>` (custom emoji) or `<a:name:id>` (animated)
    once you've uploaded icons to a server York can see. Plain unicode glyphs
    are kept here as safe fallbacks so nothing breaks before you do that.
    """

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


@dataclass(frozen=True)
class Settings:
    discord_token: str = field(default_factory=lambda: os.getenv("DISCORD_BOT_TOKEN", ""))
    openai_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("YORK_MODEL", "gpt-4o-mini"))

    bot_name: str = "York"
    creator: str = "Berry"

    wake_phrases: tuple[str, ...] = ("hey york", "hi york", "yo york", "york,", "york!")
    detach_phrases: tuple[str, ...] = (
        "enough",
        "done",
        "set free",
        "detach",
        "goodbye",
        "bye york",
        "stand down",
    )

    accent_color: int = 0x6E5BFF  # York's signature lavender-violet
    success_color: int = 0x4ADE80
    warn_color: int = 0xFACC15
    danger_color: int = 0xF87171

    proactive_min_minutes: int = 35
    proactive_max_minutes: int = 95

    history_limit: int = 12

    emoji: Emoji = field(default_factory=Emoji)


settings = Settings()
