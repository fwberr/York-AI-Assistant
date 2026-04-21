"""Moderation cog — mute, unmute, kick, ban, unban, warn, purge, slowmode, lock."""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import embeds
from ..config import settings


def _parse_duration(text: str) -> Optional[timedelta]:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        amount, unit = int(text[:-1]), text[-1].lower()
        return timedelta(seconds=amount * units[unit])
    except Exception:
        return None


class Moderation(commands.Cog):
    """Moderation commands. ALL of these require Discord permissions —
    a regular member with no mod perms cannot run them, neither via prefix
    nor via slash. Slash commands are also hidden from non-mods in the UI
    via `default_permissions`.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- KICK ----------
    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @commands.has_permissions(kick_members=True)
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(member="Member to kick", reason="Why")
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        await member.kick(reason=f"{ctx.author}: {reason}")
        await ctx.send(embed=embeds.mod_action("Member kicked", member, ctx.author, reason, settings.warn_color))

    # ---------- BAN ----------
    @commands.hybrid_command(name="ban", description="Ban a member.")
    @commands.has_permissions(ban_members=True)
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(member="Member to ban", reason="Why", delete_days="Days of msgs to wipe (0-7)")
    async def ban(self, ctx: commands.Context, member: discord.Member, delete_days: int = 0, *, reason: str = "No reason provided"):
        await member.ban(reason=f"{ctx.author}: {reason}", delete_message_days=max(0, min(7, delete_days)))
        await ctx.send(embed=embeds.mod_action("Member banned", member, ctx.author, reason, settings.danger_color))

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
            await ctx.send(embed=embeds.danger("User not found", "I couldn't find that user in the ban list."))
            return
        await ctx.guild.unban(target, reason=f"{ctx.author}: unban")
        await ctx.send(embed=embeds.mod_action("Member unbanned", target, ctx.author, "Unbanned", settings.success_color))

    # ---------- MUTE / TIMEOUT ----------
    @commands.hybrid_command(name="mute", description="Timeout a member. Duration like 10m, 1h, 1d.")
    @commands.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Member", duration="e.g. 10m, 2h, 1d", reason="Why")
    async def mute(self, ctx: commands.Context, member: discord.Member, duration: str = "10m", *, reason: str = "No reason provided"):
        td = _parse_duration(duration)
        if td is None or td.total_seconds() < 1:
            await ctx.send(embed=embeds.danger("Invalid duration", "Use formats like `10m`, `2h`, `1d`."))
            return
        await member.timeout(td, reason=f"{ctx.author}: {reason}")
        e = embeds.mod_action(f"Muted for {duration}", member, ctx.author, reason, settings.warn_color)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="unmute", description="Remove timeout from a member.")
    @commands.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Lifted"):
        await member.timeout(None, reason=f"{ctx.author}: {reason}")
        await ctx.send(embed=embeds.mod_action("Member unmuted", member, ctx.author, reason, settings.success_color))

    # ---------- WARN ----------
    @commands.hybrid_command(name="warn", description="Warn a member (DM + log).")
    @commands.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        try:
            await member.send(embed=embeds.warn(
                f"Warning from {ctx.guild.name}",
                f"**Reason:** {reason}\n**Moderator:** {ctx.author}",
            ))
        except discord.Forbidden:
            pass
        await ctx.send(embed=embeds.mod_action("Member warned", member, ctx.author, reason, settings.warn_color))

    # ---------- PURGE ----------
    @commands.hybrid_command(name="purge", description="Delete the last N messages in this channel.")
    @commands.has_permissions(manage_messages=True)
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int = 10):
        amount = max(1, min(100, amount))
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=amount + (0 if ctx.interaction else 1))
        msg = embeds.success("Purge complete", f"Removed **{len(deleted)}** messages.")
        if ctx.interaction:
            await ctx.interaction.followup.send(embed=msg, ephemeral=True)
        else:
            await ctx.send(embed=msg, delete_after=6)

    # ---------- SLOWMODE ----------
    @commands.hybrid_command(name="slowmode", description="Set channel slowmode in seconds (0 to disable).")
    @commands.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int = 0):
        seconds = max(0, min(21600, seconds))
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(embed=embeds.success("Slowmode updated", f"Now **{seconds}s** between messages."))

    # ---------- LOCK / UNLOCK ----------
    @commands.hybrid_command(name="lock", description="Lock this channel for @everyone.")
    @commands.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: lock")
        await ctx.send(embed=embeds.warn("Channel locked", "@everyone can no longer send messages here."))

    @commands.hybrid_command(name="unlock", description="Unlock this channel for @everyone.")
    @commands.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: unlock")
        await ctx.send(embed=embeds.success("Channel unlocked", "Channel is open again."))

    # ---------- ROLE ASSIGN ----------
    @commands.hybrid_command(name="addrole", description="Give a role to a member.")
    @commands.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    async def addrole(self, ctx: commands.Context, member: discord.Member, *, role: discord.Role):
        await member.add_roles(role, reason=f"{ctx.author}: addrole")
        await ctx.send(embed=embeds.success("Role granted", f"{member.mention} now has {role.mention}."))

    @commands.hybrid_command(name="removerole", description="Remove a role from a member.")
    @commands.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    async def removerole(self, ctx: commands.Context, member: discord.Member, *, role: discord.Role):
        await member.remove_roles(role, reason=f"{ctx.author}: removerole")
        await ctx.send(embed=embeds.warn("Role removed", f"{role.mention} taken from {member.mention}."))

    # ---------- ERROR HANDLER ----------
    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
            await ctx.send(embed=embeds.danger(
                "Not allowed",
                "Only server moderators can run that command. You're missing the required permission.",
            ), ephemeral=True if ctx.interaction else False)
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=embeds.danger("Bad input", str(error)))
        else:
            await ctx.send(embed=embeds.danger("Action failed", f"`{error.__class__.__name__}: {error}`"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
