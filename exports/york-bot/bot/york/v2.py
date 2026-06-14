"""Discord Components V2 message builders for discord.py 2.7.1.

Correct API signatures (verified against discord.py 2.7.1 source):
  Container(*children, accent_colour=None, accent_color=None, spoiler=False, id=None)
  Section(*children, accessory, id=None)          -- accessory is REQUIRED
  TextDisplay(content, *, id=None)
  Separator(*, visible=True, spacing=SeparatorSpacing.small, id=None)
  Thumbnail(media, *, description=None, spoiler=False, id=None)
"""
from __future__ import annotations

from typing import Any

import discord

from .config import settings

# Message flag that tells Discord to render as Components V2 layout.
_V2_FLAGS = discord.MessageFlags(components_v2=True)

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
# Low-level component factories
# ---------------------------------------------------------------------------
def _text(content: str) -> discord.ui.TextDisplay:
    return discord.ui.TextDisplay(content)


def _sep(large: bool = False) -> discord.ui.Separator:
    spacing = discord.SeparatorSpacing.large if large else discord.SeparatorSpacing.small
    return discord.ui.Separator(spacing=spacing)


def _thumb(url: str) -> discord.ui.Thumbnail:
    return discord.ui.Thumbnail(url)


def _header_item(
    header_md: str,
    thumbnail_url: str | None = None,
) -> discord.ui.Item:
    """Return a Section (with thumbnail) or plain TextDisplay (without)."""
    txt = _text(header_md)
    if thumbnail_url:
        # Section requires accessory= — pass the thumbnail there.
        return discord.ui.Section(txt, accessory=_thumb(thumbnail_url))
    return txt


# ---------------------------------------------------------------------------
# High-level container builder
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
) -> discord.ui.Container:
    """Build a Components V2 Container message.

    Parameters
    ----------
    style:          "info" | "success" | "warn" | "danger"
    title:          Bold heading text
    body:           Optional subtitle shown under the heading
    fields:         List of (label, value) pairs
    thumbnail_url:  Small image beside the title
    footer:         Small grey text at the bottom
    extra_sections: Additional (content, optional_thumbnail_url) pairs
    """
    items: list[discord.ui.Item] = []

    # ---- header ----
    header_md = f"## {title}"
    if body:
        header_md += f"\n{body}"
    items.append(_header_item(header_md, thumbnail_url))

    # ---- fields block ----
    if fields:
        items.append(_sep())
        field_lines = "\n".join(f"**{k}** · {v}" for k, v in fields)
        items.append(_text(field_lines))

    # ---- extra sections ----
    if extra_sections:
        for content, thumb in extra_sections:
            items.append(_sep())
            items.append(_header_item(content, thumb))

    # ---- footer ----
    if footer:
        items.append(_sep())
        items.append(_text(f"-# {footer}"))

    return discord.ui.Container(*items, accent_colour=_col(style))


# ---------------------------------------------------------------------------
# Preset builders
# ---------------------------------------------------------------------------
def info(title: str, body: str = "", **kw: Any) -> discord.ui.Container:
    kw.setdefault("footer", f"{settings.bot_name} · built by {settings.creator}")
    return build("info", f"{settings.emoji.info}  {title}", body, **kw)


def success(title: str, body: str = "", **kw: Any) -> discord.ui.Container:
    kw.setdefault("footer", f"{settings.bot_name} · built by {settings.creator}")
    return build("success", f"{settings.emoji.ok}  {title}", body, **kw)


def warn(title: str, body: str = "", **kw: Any) -> discord.ui.Container:
    kw.setdefault("footer", f"{settings.bot_name} · built by {settings.creator}")
    return build("warn", f"{settings.emoji.warn}  {title}", body, **kw)


def danger(title: str, body: str = "", **kw: Any) -> discord.ui.Container:
    kw.setdefault("footer", f"{settings.bot_name} · built by {settings.creator}")
    return build("danger", f"{settings.emoji.error}  {title}", body, **kw)


def mod_action(
    action: str,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str,
    style: str = "info",
    extra_fields: list[tuple[str, str]] | None = None,
) -> discord.ui.Container:
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
    container: discord.ui.Container,
    *,
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
    reference: discord.Message | None = None,
) -> discord.Message:
    kwargs: dict[str, Any] = {"components": [container], "flags": _V2_FLAGS}
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
    container: discord.ui.Container,
    *,
    view: discord.ui.View | None = None,
) -> None:
    kwargs: dict[str, Any] = {"components": [container], "flags": _V2_FLAGS}
    if view is not None:
        kwargs["view"] = view
    await message.edit(**kwargs)
