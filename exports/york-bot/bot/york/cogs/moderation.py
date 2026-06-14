"""Moderation cog — mute, unmute, kick, ban, unban, warn, warnings, purge, slowmode, lock."""
from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import v2
from ..config import settings

# ---------------------------------------------------------------------------
# Warning store
# ---------------------------------------------------------------------------
_WARN_VERSION = 1


def _warn_path() -> Path:
    p = settings.data_dir / "warnings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_warns() -> dict:
    p = _warn_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _save_warns(d: dict) -> None:
    _warn_path().write_text(json.dumps(d, indent=2))


def _guild_key(guild_id: int) -> str:
    return str(guild_id)


def _user_key(user_id: int) -> str:
    return str(user_id)


def _get_warns(d: dict, guild_id: int, user_id: int) -> list[dict]:
    return d.setdefault(_guild_key(guild_id), {}).setdefault(_user_key(user_id), [])


def _add_warn(guild_id: int, user_id: int, reason: str, mod_id: int, mod_name: str) -> int:
    d = _load_warns()
    warns = _get_warns(d, guild_id, user_id)
    new_id = (max((w["id"] for w in warns), default=0)) + 1
    warns.append({
        "id": new_id,
        "reason": reason,
        "mod_id": mod_id,
        "mod_name": mod_name,
        "ts": int(time.time()),
    })
    _save_warns(d)
    return new_id


def _count_warns(guild_id: int, user_id: int) -> int:
    d = _load_warns()
    return len(_get_warns(d, guild_id, user_id))


def _list_warns(guild_id: int, user_id: int) -> list[dict]:
    d = _load_warns()
    return list(_get_warns(d, guild_id, user_id))


def _del_warn(guild_id: int, user_id: int, warn_id: int) -> bool:
    d = _load_warns()
    warns = _get_warns(d, guild_id, user_id)
    before = len(warns)
    updated = [w for w in warns if w["id"] != warn_id]
    if len(updated) == before:
        return False
    d[_guild_key(guild_id)][_user_key(user_id)] = updated
    _save_warns(d)
    return True


def _clear_warns(guild_id: int, user_id: int) -> int:
    d = _load_warns()
    warns = _get_warns(d, guild_id, user_id)
    count = len(warns)
    d[_guild_key(guild_id)][_user_key(user_id)] = []
    _save_warns(d)
    return count


# ---------------------------------------------------------------------------
# Duration parser
# ---------------------------------------------------------------------------
def _parse_duration(text: str) -> Optional[timedelta]:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        amount, unit = int(text[:-1]), text[-1].lower()
        return timedelta(seconds=amount * units[unit])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- KICK ----------
    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @commands.has_permissions(kick_members=True)
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(member="Member to kick", reason="Why")
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        await member.kick(reason=f"{ctx.author}: {reason}")
        await v2.send(ctx, v2.mod_action("Member Kicked", member, ctx.author, reason, style="warn"))

    # ---------- BAN ----------
    @commands.hybrid_command(name="ban", description="Ban a member.")
    @commands.has_permissions(ban_members=True)
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(member="Member to ban", reason="Why", delete_days="Days of msgs to wipe (0-7)")
    async def ban(self, ctx: commands.Context, member: discord.Member, delete_days: int = 0, *, reason: str = "No reason provided"):
        await member.ban(reason=f"{ctx.author}: {reason}", delete_message_days=max(0, min(7, delete_days)))
        await v2.send(ctx, v2.mod_action("Member Banned", member, ctx.author, reason, style="danger"))

    # ---------- UNBAN ----------
    @commands.hybrid_command(name="unban", description="Unban a user by ID or name#tag.")
    @commands.has_permissions(ban_members=True)
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, *, user: str):
        target = None
        async for entry in ctx.guild.bans():
            if str(entry.user) == user or str(entry.user.id) == user or entry.user.name == user:
                target = entry.user
                break
        if not target:
            await v2.send(ctx, v2.danger("User Not Found", "That user was not found in the ban list."))
            return
        await ctx.guild.unban(target, reason=f"{ctx.author}: unban")
        await v2.send(ctx, v2.mod_action("Member Unbanned", target, ctx.author, "Unbanned", style="success"))

    # ---------- MUTE / TIMEOUT ----------
    @commands.hybrid_command(name="mute", description="Timeout a member. Duration like 10m, 1h, 1d.")
    @commands.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member", duration="e.g. 10m, 2h, 1d", reason="Why")
    async def mute(self, ctx: commands.Context, member: discord.Member, duration: str = "10m", *, reason: str = "No reason provided"):
        td = _parse_duration(duration)
        if td is None or td.total_seconds() < 1:
            await v2.send(ctx, v2.danger("Invalid Duration", "Use formats like `10m`, `2h`, `1d`."))
            return
        await member.timeout(td, reason=f"{ctx.author}: {reason}")
        await v2.send(ctx, v2.mod_action(f"Member Muted ({duration})", member, ctx.author, reason, style="warn"))

    @commands.hybrid_command(name="unmute", description="Remove timeout from a member.")
    @commands.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Lifted"):
        await member.timeout(None, reason=f"{ctx.author}: {reason}")
        await v2.send(ctx, v2.mod_action("Member Unmuted", member, ctx.author, reason, style="success"))

    # ---------- WARN ----------
    @commands.hybrid_command(name="warn", description="Warn a member (DM + log + stores warning).")
    @commands.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member to warn", reason="Reason for the warning")
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        if not ctx.guild:
            return
        warn_id = _add_warn(ctx.guild.id, member.id, reason, ctx.author.id, str(ctx.author))
        total = _count_warns(ctx.guild.id, member.id)

        try:
            dm_c = v2.build(
                "warn",
                f"{settings.emoji.warn}  Warning from {ctx.guild.name}",
                "You have received an official warning.",
                fields=[
                    ("Reason", reason),
                    ("Moderator", str(ctx.author)),
                    ("Warning ID", f"#{warn_id}"),
                    ("Total Warnings", str(total)),
                ],
                footer=f"{settings.bot_name} · built by {settings.creator}",
            )
            await member.send(components=[dm_c], flags=discord.MessageFlags(components_v2=True))
        except discord.Forbidden:
            pass

        container = v2.mod_action(
            "Member Warned",
            member,
            ctx.author,
            reason,
            style="warn",
            extra_fields=[
                ("Warning ID", f"#{warn_id}"),
                ("Total Warnings", str(total)),
            ],
        )
        await v2.send(ctx, container)

    # ---------- WARNINGS (list) ----------
    @commands.hybrid_command(name="warnings", description="View all warnings for a member.")
    @commands.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member to check")
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        if not ctx.guild:
            return
        warns = _list_warns(ctx.guild.id, member.id)
        if not warns:
            await v2.send(ctx, v2.info(
                f"Warnings — {member.display_name}",
                "This member has no recorded warnings.",
                thumbnail_url=member.display_avatar.url,
            ))
            return

        lines = []
        for w in warns:
            ts = f"<t:{w['ts']}:d>" if w.get("ts") else "unknown date"
            lines.append(f"**#{w['id']}** · {w['reason']} — *{w['mod_name']}* · {ts}")

        body = "\n".join(lines)
        container = v2.build(
            "warn",
            f"{settings.emoji.warn}  Warnings — {member.display_name}",
            f"{len(warns)} warning{'s' if len(warns) != 1 else ''} on record.",
            fields=None,
            thumbnail_url=member.display_avatar.url,
            extra_sections=[(body, None)],
            footer=f"Use !delwarn @user <id> to remove one · !clearwarns @user to clear all",
        )
        await v2.send(ctx, container)

    # ---------- DELWARN ----------
    @commands.hybrid_command(name="delwarn", description="Delete a specific warning by ID.")
    @commands.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member", warn_id="Warning ID to delete (see !warnings)")
    async def delwarn(self, ctx: commands.Context, member: discord.Member, warn_id: int):
        if not ctx.guild:
            return
        removed = _del_warn(ctx.guild.id, member.id, warn_id)
        if not removed:
            await v2.send(ctx, v2.danger(
                "Warning Not Found",
                f"Warning **#{warn_id}** does not exist for {member.mention}.",
            ))
            return
        remaining = _count_warns(ctx.guild.id, member.id)
        await v2.send(ctx, v2.success(
            "Warning Removed",
            f"Warning **#{warn_id}** has been deleted from {member.mention}'s record.\n"
            f"They now have **{remaining}** warning{'s' if remaining != 1 else ''} remaining.",
        ))

    # ---------- CLEARWARNS ----------
    @commands.hybrid_command(name="clearwarns", description="Clear ALL warnings for a member.")
    @commands.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member to clear all warnings for")
    async def clearwarns(self, ctx: commands.Context, member: discord.Member):
        if not ctx.guild:
            return
        count = _clear_warns(ctx.guild.id, member.id)
        await v2.send(ctx, v2.success(
            "Warnings Cleared",
            f"All **{count}** warning{'s' if count != 1 else ''} for {member.mention} have been removed.",
            thumbnail_url=member.display_avatar.url,
        ))

    # ---------- PURGE ----------
    @commands.hybrid_command(name="purge", description="Delete the last N messages in this channel.")
    @commands.has_permissions(manage_messages=True)
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int = 10):
        amount = max(1, min(100, amount))
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=amount + (0 if ctx.interaction else 1))
        container = v2.success("Purge Complete", f"Removed **{len(deleted)}** messages.")
        if ctx.interaction:
            await ctx.interaction.followup.send(
                components=[container],
                flags=discord.MessageFlags(components_v2=True),
                ephemeral=True,
            )
        else:
            await v2.send(ctx, container)

    # ---------- SLOWMODE ----------
    @commands.hybrid_command(name="slowmode", description="Set channel slowmode in seconds (0 to disable).")
    @commands.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int = 0):
        seconds = max(0, min(21600, seconds))
        await ctx.channel.edit(slowmode_delay=seconds)
        await v2.send(ctx, v2.success("Slowmode Updated", f"Now **{seconds}s** between messages."))

    # ---------- LOCK / UNLOCK ----------
    @commands.hybrid_command(name="lock", description="Lock this channel for @everyone.")
    @commands.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: lock")
        await v2.send(ctx, v2.warn("Channel Locked", "Members can no longer send messages here."))

    @commands.hybrid_command(name="unlock", description="Unlock this channel for @everyone.")
    @commands.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: unlock")
        await v2.send(ctx, v2.success("Channel Unlocked", "The channel is open again."))

    # ---------- ROLE ASSIGN ----------
    @commands.hybrid_command(name="addrole", description="Give a role to a member.")
    @commands.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    async def addrole(self, ctx: commands.Context, member: discord.Member, *, role: discord.Role):
        await member.add_roles(role, reason=f"{ctx.author}: addrole")
        await v2.send(ctx, v2.success("Role Granted", f"{member.mention} now has {role.mention}."))

    @commands.hybrid_command(name="removerole", description="Remove a role from a member.")
    @commands.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    async def removerole(self, ctx: commands.Context, member: discord.Member, *, role: discord.Role):
        await member.remove_roles(role, reason=f"{ctx.author}: removerole")
        await v2.send(ctx, v2.warn("Role Removed", f"{role.mention} taken from {member.mention}."))

    # ---------- ERROR HANDLER ----------
    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
            await v2.send(ctx, v2.danger(
                "Not Allowed",
                "Only server moderators can run that command.",
            ), ephemeral=bool(ctx.interaction))
        elif isinstance(error, commands.BadArgument):
            await v2.send(ctx, v2.danger("Bad Input", str(error)))
        else:
            await v2.send(ctx, v2.danger("Action Failed", f"`{error.__class__.__name__}: {error}`"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
