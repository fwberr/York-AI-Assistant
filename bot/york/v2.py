"""Discord embed message builders for discord.py 2.7.1.

Uses standard discord.Embed so responses work in every context:
prefix commands, slash commands, hybrid commands, and DMs.
"""
from __future__ import annotations

from typing import Any

import discord

from .config import settings

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
_COLORS: dict[str, int] = {
    "info":    settings.accent_color,
    "success": settings.success_color,
    "warn":    settings.warn_color,
    "danger":  settings.danger_color,
}


def _col(style: str) -> int:
    return _COLORS.get(style, settings.accent_color)


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------
def build(
    style: str,
    title: str,
    body: str = "",
    *,
    fields: list[tuple[str, str]] | None = None,
    thumbnail_url: str | None = None,
    footer: str | None = None,
    extra_sections: list[tuple[str, str | None]] | None = None,
) -> discord.Embed:
    """Build a styled Discord embed.

    Parameters
    ----------
    style:          "info" | "success" | "warn" | "danger"
    title:          Embed title
    body:           Optional description shown under the title
    fields:         List of (label, value) pairs added as inline fields
    thumbnail_url:  Small image in the top-right corner
    footer:         Small grey text at the bottom
    extra_sections: Additional (content, optional_thumbnail_url) pairs
                    appended as non-inline fields
    """
    embed = discord.Embed(
        title=title,
        description=body or None,
        color=_col(style),
    )

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    if fields:
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=True)

    if extra_sections:
        for content, thumb in extra_sections:
            embed.add_field(name="\u200b", value=content, inline=False)
            if thumb:
                embed.set_image(url=thumb)

    if footer:
        embed.set_footer(text=footer)

    return embed


# ---------------------------------------------------------------------------
# Preset builders
# ---------------------------------------------------------------------------
def info(title: str, body: str = "", **kw: Any) -> discord.Embed:
    kw.setdefault("footer", f"{settings.bot_name} · built by {settings.creator}")
    return build("info", f"{settings.emoji.info}  {title}", body, **kw)


def success(title: str, body: str = "", **kw: Any) -> discord.Embed:
    kw.setdefault("footer", f"{settings.bot_name} · built by {settings.creator}")
    return build("success", f"{settings.emoji.ok}  {title}", body, **kw)


def warn(title: str, body: str = "", **kw: Any) -> discord.Embed:
    kw.setdefault("footer", f"{settings.bot_name} · built by {settings.creator}")
    return build("warn", f"{settings.emoji.warn}  {title}", body, **kw)


def danger(title: str, body: str = "", **kw: Any) -> discord.Embed:
    kw.setdefault("footer", f"{settings.bot_name} · built by {settings.creator}")
    return build("danger", f"{settings.emoji.error}  {title}", body, **kw)


def mod_action(
    action: str,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str,
    style: str = "info",
    extra_fields: list[tuple[str, str]] | None = None,
) -> discord.Embed:
    fields: list[tuple[str, str]] = [
        ("Target",    f"{target.mention} `{target}`"),
        ("Moderator", moderator.mention),
        ("Reason",    reason or "No reason provided"),
    ]
    if extra_fields:
        fields.extend(extra_fields)
    return build(
        style,
        f"{settings.emoji.hammer}  {action}",
        "Action logged",
        fields=fields,
        thumbnail_url=target.display_avatar.url,
        footer=f"{settings.bot_name} · built by {settings.creator}",
    )


# ---------------------------------------------------------------------------
# Send / edit helpers
# ---------------------------------------------------------------------------
async def send(
    ctx: Any,
    embed: discord.Embed,
    *,
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
    reference: discord.Message | None = None,
) -> discord.Message:
    kwargs: dict[str, Any] = {"embed": embed}
    if view:
        kwargs["view"] = view
    if ephemeral:
        kwargs["ephemeral"] = True
    if reference:
        kwargs["reference"] = reference
        kwargs["mention_author"] = False
    return await ctx.send(**kwargs)


async def edit(
    message: discord.Message,
    embed: discord.Embed,
    *,
    view: discord.ui.View | None = None,
) -> None:
    kwargs: dict[str, Any] = {"embed": embed}
    if view is not None:
        kwargs["view"] = view
    await message.edit(**kwargs)
