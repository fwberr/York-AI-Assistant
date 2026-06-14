"""Centralised settings for York."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _resolve_ai_provider() -> tuple[str, str, str]:
    """Return (api_key, base_url, default_model) based on available env vars.

    Priority:
    1. GROQ_API_KEY          → Groq endpoint, llama-3.3-70b-versatile
    2. AI_INTEGRATIONS vars  → Replit AI proxy
    3. OPENAI_API_KEY        → OpenAI directly, gpt-4o-mini
    4. Nothing               → empty (AI offline)

    YORK_MODEL always overrides the default model if set.
    YORK_BASE_URL always overrides the base URL if set.
    """
    groq_key   = os.getenv("GROQ_API_KEY", "")
    proxy_key  = os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY", "")
    proxy_url  = os.getenv("AI_INTEGRATIONS_OPENAI_BASE_URL", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    custom_url = os.getenv("YORK_BASE_URL", "")
    custom_mdl = os.getenv("YORK_MODEL", "")

    if groq_key:
        key   = groq_key
        url   = custom_url or "https://api.groq.com/openai/v1"
        model = custom_mdl or "llama-3.3-70b-versatile"
    elif proxy_key:
        key   = proxy_key
        url   = custom_url or proxy_url
        model = custom_mdl or "gpt-4o-mini"
    elif openai_key:
        key   = openai_key
        url   = custom_url or ""
        model = custom_mdl or "gpt-4o-mini"
    else:
        key = url = model = ""

    return key, url, model


_AI_KEY, _AI_URL, _AI_MODEL = _resolve_ai_provider()


@dataclass(frozen=True)
class Emoji:
    ok: str     = os.getenv("YORK_EMOJI_OK",     "◆")
    warn: str   = os.getenv("YORK_EMOJI_WARN",   "◈")
    error: str  = os.getenv("YORK_EMOJI_ERROR",  "✖")
    info: str   = os.getenv("YORK_EMOJI_INFO",   "❖")
    spark: str  = os.getenv("YORK_EMOJI_SPARK",  "✦")
    hammer: str = os.getenv("YORK_EMOJI_HAMMER", "⚒")
    shield: str = os.getenv("YORK_EMOJI_SHIELD", "❘❘")
    boot: str   = os.getenv("YORK_EMOJI_BOOT",   "▶")
    mute: str   = os.getenv("YORK_EMOJI_MUTE",   "◑")
    member: str = os.getenv("YORK_EMOJI_MEMBER", "◉")
    role: str   = os.getenv("YORK_EMOJI_ROLE",   "◐")
    crown: str  = os.getenv("YORK_EMOJI_CROWN",  "♛")
    brain: str  = os.getenv("YORK_EMOJI_BRAIN",  "✺")
    wave: str   = os.getenv("YORK_EMOJI_WAVE",   "～")
    fish: str   = os.getenv("YORK_EMOJI_FISH",   "🎣")
    crate: str  = os.getenv("YORK_EMOJI_CRATE",  "📦")


@dataclass(frozen=True)
class Settings:
    # ---- AI credentials (resolved at startup) ----
    ai_key:   str = field(default_factory=lambda: _AI_KEY)
    ai_url:   str = field(default_factory=lambda: _AI_URL)
    ai_model: str = field(default_factory=lambda: _AI_MODEL)

    # ---- legacy aliases (kept for any code that still reads them) ----
    openai_key:     str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    proxy_key:      str = field(default_factory=lambda: os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY", ""))
    proxy_base_url: str = field(default_factory=lambda: os.getenv("AI_INTEGRATIONS_OPENAI_BASE_URL", ""))
    openai_model:   str = field(default_factory=lambda: _AI_MODEL)   # same resolved value

    # ---- Discord ----
    discord_token: str = field(default_factory=lambda: os.getenv("DISCORD_BOT_TOKEN", ""))

    bot_name: str = "York"
    creator: str  = "Berry"

    # ---- Data persistence ----
    # Set DATA_DIR to a persistent volume path on your host so player
    # data (coins, XP, marriages, warnings) survives bot updates/redeploys.
    # e.g. DATA_DIR=/data  on Render/Katabump
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "bot/data")))

    # ---- Conversation ----
    wake_phrases: tuple[str, ...] = ("hey york", "hi york", "yo york", "york,", "york!")
    detach_phrases: tuple[str, ...] = (
        "enough", "done", "set free", "detach", "goodbye", "bye york", "stand down",
    )

    # ---- Colours ----
    accent_color:  int = 0x6E5BFF
    success_color: int = 0x4ADE80
    warn_color:    int = 0xFACC15
    danger_color:  int = 0xF87171

    # ---- Proactive ----
    proactive_min_minutes: int = 35
    proactive_max_minutes: int = 95

    history_limit: int = 12

    emoji: Emoji = field(default_factory=Emoji)


settings = Settings()
