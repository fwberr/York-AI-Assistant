"""Starboard cog — react ⭐ enough times and York reposts it to the highlights channel.

Configuration is per-guild and persisted to DATA_DIR/starboard.json.
Moderators use !starboard commands to set the channel, threshold, and emoji.

Stored schema per guild:
{
  "guild_id": {
    "channel_id": 123456,     # destination channel
    "min_stars": 3,           # reactions needed
    "emoji": "⭐",            # reaction emoji to watch
    "posted": {               # original_msg_id -> starboard_msg_id
      "msg_id": "sb_msg_id"
    }
  }
}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import v2
from ..config import settings


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _cfg_path() -> Path:
    p = settings.data_dir / "starboard.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_cfg() -> dict:
    p = _cfg_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _save_cfg(d: dict) -> None:
    _cfg_path().write_text(json.dumps(d, indent=2))


def _guild_cfg(d: dict, guild_id: int) -> dict:
    return d.setdefault(str(guild_id), {
        "channel_id": None,
        "min_stars": 3,
        "emoji": "⭐",
        "posted": {},
    })


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class Starboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- configuration group --------
    @commands.group(name="starboard", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def starboard(self, ctx: commands.Context):
        """Show current starboard configuration."""
        if not ctx.guild:
            return
        d = _load_cfg()
        cfg = _guild_cfg(d, ctx.guild.id)

        ch_id = cfg.get("channel_id")
        channel = ctx.guild.get_channel(ch_id) if ch_id else None
        ch_mention = channel.mention if channel else "*not set*"

        await v2.send(ctx, v2.build(
            "info",
            f"⭐  Starboard Configuration",
            "Current settings for this server.",
            fields=[
                ("Channel",     ch_mention),
                ("Threshold",   f"{cfg.get('min_stars', 3)} {cfg.get('emoji', '⭐')} reactions"),
                ("Emoji",       cfg.get("emoji", "⭐")),
                ("Messages Highlighted", str(len(cfg.get("posted", {})))),
            ],
            footer=(
                "Commands: !starboard channel #ch · !starboard stars <n> · "
                "!starboard emoji <e> · !starboard reset"
            ),
        ))

    @starboard.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def sb_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where starred messages are posted."""
        d = _load_cfg()
        cfg = _guild_cfg(d, ctx.guild.id)
        cfg["channel_id"] = channel.id
        _save_cfg(d)
        await v2.send(ctx, v2.success(
            "Starboard Channel Set",
            f"Starred messages will be posted in {channel.mention}.",
        ))

    @starboard.command(name="stars")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def sb_stars(self, ctx: commands.Context, count: int):
        """Set how many star reactions a message needs."""
        count = max(1, min(50, count))
        d = _load_cfg()
        cfg = _guild_cfg(d, ctx.guild.id)
        cfg["min_stars"] = count
        _save_cfg(d)
        await v2.send(ctx, v2.success(
            "Star Threshold Updated",
            f"Messages now need **{count}** {cfg.get('emoji', '⭐')} reaction{'s' if count != 1 else ''} to appear on the starboard.",
        ))

    @starboard.command(name="emoji")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def sb_emoji(self, ctx: commands.Context, emoji: str):
        """Change which emoji triggers the starboard (default ⭐)."""
        # Strip any whitespace; accept unicode or custom emojis
        emoji = emoji.strip()
        if not emoji:
            await v2.send(ctx, v2.danger("Invalid Emoji", "Please provide a valid emoji."))
            return
        d = _load_cfg()
        cfg = _guild_cfg(d, ctx.guild.id)
        cfg["emoji"] = emoji
        _save_cfg(d)
        await v2.send(ctx, v2.success(
            "Starboard Emoji Updated",
            f"York will now watch for **{emoji}** reactions on messages.",
        ))

    @starboard.command(name="reset")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def sb_reset(self, ctx: commands.Context):
        """Clear all starboard history (does not delete the posted messages)."""
        d = _load_cfg()
        cfg = _guild_cfg(d, ctx.guild.id)
        count = len(cfg.get("posted", {}))
        cfg["posted"] = {}
        _save_cfg(d)
        await v2.send(ctx, v2.warn(
            "Starboard History Cleared",
            f"Cleared {count} tracked message{'s' if count != 1 else ''}. "
            f"Previously starred messages can be starred again.",
        ))

    # -------- reaction listener --------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._check_reaction(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._check_reaction(payload)

    async def _check_reaction(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        d = _load_cfg()
        cfg = _guild_cfg(d, payload.guild_id)

        # Starboard must be configured.
        sb_channel_id = cfg.get("channel_id")
        if not sb_channel_id:
            return

        watch_emoji = cfg.get("emoji", "⭐")
        min_stars   = cfg.get("min_stars", 3)

        # Check if this reaction matches the watched emoji.
        reaction_str = (
            str(payload.emoji)
            if payload.emoji.is_unicode_emoji()
            else f"<:{payload.emoji.name}:{payload.emoji.id}>"
        )
        if reaction_str != watch_emoji and str(payload.emoji) != watch_emoji:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        # Don't star messages posted IN the starboard channel itself.
        if payload.channel_id == sb_channel_id:
            return

        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return

        # Count unique human reactors (bots don't count).
        star_count = 0
        for reaction in message.reactions:
            r_str = (
                str(reaction.emoji)
                if isinstance(reaction.emoji, str)
                else (
                    str(reaction.emoji)
                    if reaction.emoji.is_unicode_emoji()
                    else f"<:{reaction.emoji.name}:{reaction.emoji.id}>"
                )
            )
            if r_str == watch_emoji or str(reaction.emoji) == watch_emoji:
                # Fetch users to exclude bots.
                try:
                    users = [u async for u in reaction.users()]
                    star_count = sum(1 for u in users if not u.bot)
                except Exception:
                    star_count = reaction.count
                break

        posted: dict = cfg.setdefault("posted", {})
        msg_key = str(payload.message_id)
        sb_channel = guild.get_channel(sb_channel_id)
        if not isinstance(sb_channel, discord.TextChannel):
            return

        if star_count >= min_stars:
            if msg_key in posted:
                # Already posted — update the star count on the existing post.
                try:
                    sb_msg = await sb_channel.fetch_message(int(posted[msg_key]))
                    await self._edit_starboard_message(sb_msg, message, star_count, watch_emoji)
                except (discord.NotFound, discord.Forbidden):
                    del posted[msg_key]
                    _save_cfg(d)
            else:
                # Post for the first time.
                try:
                    sb_msg = await self._post_to_starboard(
                        sb_channel, message, star_count, watch_emoji
                    )
                    posted[msg_key] = str(sb_msg.id)
                    _save_cfg(d)
                except discord.Forbidden:
                    pass
        else:
            # Stars dropped below threshold — update the count if already posted.
            if msg_key in posted:
                try:
                    sb_msg = await sb_channel.fetch_message(int(posted[msg_key]))
                    await self._edit_starboard_message(sb_msg, message, star_count, watch_emoji)
                except (discord.NotFound, discord.Forbidden):
                    pass

    def _star_tier(self, count: int) -> str:
        """Decoration that changes with star count."""
        if count >= 15:
            return "🌟"
        if count >= 8:
            return "✨"
        return "⭐"

    async def _build_starboard_container(
        self,
        message: discord.Message,
        star_count: int,
        watch_emoji: str,
    ) -> discord.ui.Container:
        author = message.author
        jump = f"[Jump to message]({message.jump_url})"
        channel_ref = f"<#{message.channel.id}>"

        body = message.content or "*No text content.*"
        if len(body) > 800:
            body = body[:800] + "…"

        tier = self._star_tier(star_count)
        fields = [
            ("Stars",   f"{tier} **{star_count}** {watch_emoji}"),
            ("Channel", channel_ref),
            ("Author",  author.mention),
            ("Posted",  f"<t:{int(message.created_at.timestamp())}:R>"),
            ("Link",    jump),
        ]

        # Include first image attachment if present.
        extra: list[tuple[str, str | None]] = []
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                extra.append((f"[View attachment]({att.url})", None))
                break

        return v2.build(
            "warn",  # gold accent fits the starboard vibe
            f"{tier}  Starred Message",
            body,
            fields=fields,
            thumbnail_url=author.display_avatar.url,
            extra_sections=extra if extra else None,
            footer=f"{settings.bot_name} · built by {settings.creator}",
        )

    async def _post_to_starboard(
        self,
        sb_channel: discord.TextChannel,
        message: discord.Message,
        star_count: int,
        watch_emoji: str,
    ) -> discord.Message:
        container = await self._build_starboard_container(message, star_count, watch_emoji)
        return await sb_channel.send(
            components=[container],
            flags=discord.MessageFlags(is_components_v2=True),
        )

    async def _edit_starboard_message(
        self,
        sb_msg: discord.Message,
        original: discord.Message,
        star_count: int,
        watch_emoji: str,
    ) -> None:
        container = await self._build_starboard_container(original, star_count, watch_emoji)
        await sb_msg.edit(
            components=[container],
            flags=discord.MessageFlags(is_components_v2=True),
        )

    # -------- error handler --------
    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
            await v2.send(ctx, v2.danger(
                "Not Allowed",
                "You need **Manage Server** permission to configure the starboard.",
            ), ephemeral=bool(ctx.interaction))
        else:
            await v2.send(ctx, v2.danger("Error", f"`{error.__class__.__name__}: {error}`"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Starboard(bot))
