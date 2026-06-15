"""Centralised settings for York."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _resolve_ai_provider() -> tuple[str, str, str]:
    """Return (api_key, base_url, default_model) based on available env vars.

    Priority:
    1. GEMINI_API_KEY        → Google Gemini 2.0 Flash (free, 1500/day, no IP blocks)
    2. GROQ_API_KEY          → Groq endpoint, llama-3.3-70b-versatile
    3. AI_INTEGRATIONS vars  → Replit AI proxy
    4. OPENAI_API_KEY        → OpenAI directly, gpt-4o-mini
    5. Nothing               → empty (AI offline)

    YORK_MODEL always overrides the default model if set.
    YORK_BASE_URL always overrides the base URL if set.
    """
    mistral_key = os.getenv("MISTRAL_API_KEY", "")
    gemini_key  = os.getenv("GEMINI_API_KEY", "")
    groq_key    = os.getenv("GROQ_API_KEY", "")
    proxy_key   = os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY", "")
    proxy_url   = os.getenv("AI_INTEGRATIONS_OPENAI_BASE_URL", "")
    openai_key  = os.getenv("OPENAI_API_KEY", "")
    custom_url  = os.getenv("YORK_BASE_URL", "")
    custom_mdl  = os.getenv("YORK_MODEL", "")

    if mistral_key:
        # Mistral: free tier, OpenAI-compatible, works from cloud hosting.
        key   = mistral_key
        url   = custom_url or "https://api.mistral.ai/v1"
        model = custom_mdl or "mistral-small-latest"
    elif gemini_key:
        # Gemini native REST API (via aiohttp in ai.py).
        key   = gemini_key
        url   = custom_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
        model = custom_mdl or "gemini-2.0-flash"
    elif groq_key:
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


def _resolve_data_dir() -> Path:
    """Return a writable data directory, falling back gracefully if the
    configured path isn't accessible (e.g. Render free tier without a disk)."""
    import logging
    candidates = [
        os.getenv("DATA_DIR", ""),
        "bot/data",
        "/tmp/york_data",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        p = Path(candidate)
        try:
            p.mkdir(parents=True, exist_ok=True)
            # Quick write-test
            test = p / ".write_test"
            test.touch()
            test.unlink()
            return p
        except (PermissionError, OSError):
            logging.getLogger("york.config").warning(
                "DATA_DIR %s is not writable, trying fallback…", candidate
            )
    # Last-resort: current working directory
    return Path(".")


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
    # e.g. DATA_DIR=/opt/render/project/src/data  on Render (free tier)
    #      DATA_DIR=/data  on Render paid tier with a mounted disk
    data_dir: Path = field(default_factory=lambda: _resolve_data_dir())

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
