"""Embed factory so every York message has a consistent identity."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Tuple

import discord

from .config import settings


def _base(color: int, title: str | None, description: str | None) -> discord.Embed:
    e = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    e.set_footer(text=f"{settings.bot_name} · built by {settings.creator}")
    return e


def info(title: str, description: str = "") -> discord.Embed:
    return _base(settings.accent_color, f"{settings.emoji.info}  {title}", description)


def success(title: str, description: str = "") -> discord.Embed:
    return _base(settings.success_color, f"{settings.emoji.ok}  {title}", description)


def warn(title: str, description: str = "") -> discord.Embed:
    return _base(settings.warn_color, f"{settings.emoji.warn}  {title}", description)


def danger(title: str, description: str = "") -> discord.Embed:
    return _base(settings.danger_color, f"{settings.emoji.error}  {title}", description)


def mod_action(
    action: str,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str,
    color: int | None = None,
) -> discord.Embed:
    e = _base(
        color or settings.accent_color,
        f"{settings.emoji.hammer}  {action}",
        None,
    )
    e.add_field(name="Target", value=f"{target.mention} `({target})`", inline=True)
    e.add_field(name="Moderator", value=moderator.mention, inline=True)
    e.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    return e


def fields_embed(title: str, fields: Iterable[Tuple[str, str, bool]], color: int | None = None) -> discord.Embed:
    e = _base(color or settings.accent_color, f"{settings.emoji.info}  {title}", None)
    for name, value, inline in fields:
        e.add_field(name=name, value=value, inline=inline)
    return e
