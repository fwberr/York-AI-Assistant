"""Server insights — info, members, roles, channels, user lookup."""
from __future__ import annotations

from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from .. import v2
from ..config import settings


class RoleSelect(discord.ui.Select):
    def __init__(self, roles: List[discord.Role]):
        options = [
            discord.SelectOption(
                label=(r.name or "role")[:90],
                value=str(r.id),
                description=f"{len(r.members)} members · pos {r.position}"[:90],
            )
            for r in roles[:25]
        ]
        super().__init__(placeholder="Inspect a role…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        if not role:
            await interaction.response.send_message("Role not found.", ephemeral=True)
            return
        container = v2.build(
            "info",
            f"{settings.emoji.role}  Role · {role.name}",
            fields=[
                ("Members", str(len(role.members))),
                ("Color", str(role.color)),
                ("Hoisted", "Yes" if role.hoist else "No"),
                ("Mentionable", "Yes" if role.mentionable else "No"),
                ("Position", str(role.position)),
                ("Created", discord.utils.format_dt(role.created_at, "R")),
            ],
        )
        await interaction.response.send_message(
            components=[container],
            flags=discord.MessageFlags(components_v2=True),
            ephemeral=True,
        )


class RoleView(discord.ui.View):
    def __init__(self, roles: List[discord.Role]):
        super().__init__(timeout=120)
        self.add_item(RoleSelect(roles))


class Insights(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="serverinfo", description="Show insights about this server.")
    async def serverinfo(self, ctx: commands.Context):
        g = ctx.guild
        humans = sum(1 for m in g.members if not m.bot)
        bots = g.member_count - humans
        container = v2.build(
            "info",
            f"{settings.emoji.crown}  {g.name}",
            f"Server ID `{g.id}`",
            fields=[
                ("Owner", g.owner.mention if g.owner else "—"),
                ("Created", discord.utils.format_dt(g.created_at, "R")),
                ("Members", f"{g.member_count} total · {humans} humans · {bots} bots"),
                ("Channels", f"{len(g.text_channels)} text · {len(g.voice_channels)} voice"),
                ("Roles", str(len(g.roles))),
                ("Boosts", f"Tier {g.premium_tier} · {g.premium_subscription_count} boosts"),
            ],
            thumbnail_url=g.icon.url if g.icon else None,
        )
        await v2.send(ctx, container)

    @commands.hybrid_command(name="userinfo", description="Show details about a member.")
    async def userinfo(self, ctx: commands.Context, member: discord.Member | None = None):
        m = member or ctx.author
        roles = ", ".join(r.mention for r in reversed(m.roles[1:])) or "—"
        container = v2.build(
            "info",
            f"{settings.emoji.member}  {m.display_name}",
            f"Tag: `{m}` · ID: `{m.id}`",
            fields=[
                ("Joined Server", discord.utils.format_dt(m.joined_at, "R") if m.joined_at else "—"),
                ("Account Created", discord.utils.format_dt(m.created_at, "R")),
                ("Top Role", m.top_role.mention),
                ("Bot", "Yes" if m.bot else "No"),
            ],
            extra_sections=[(f"**Roles ({len(m.roles)-1})**\n{roles[:1000]}", None)],
            thumbnail_url=m.display_avatar.url,
        )
        await v2.send(ctx, container)

    @commands.hybrid_command(name="roles", description="List server roles (interactive).")
    async def roles(self, ctx: commands.Context):
        roles = sorted([r for r in ctx.guild.roles if not r.is_default()], key=lambda r: -r.position)
        if not roles:
            await v2.send(ctx, v2.info("Roles", "No custom roles on this server."))
            return
        preview = "\n".join(
            f"{settings.emoji.role} {r.mention} — {len(r.members)} member{'s' if len(r.members) != 1 else ''}"
            for r in roles[:15]
        )
        more = f"\n*…and {len(roles)-15} more*" if len(roles) > 15 else ""
        container = v2.info(f"Roles ({len(roles)})", preview + more)
        await v2.send(ctx, container, view=RoleView(roles))

    @commands.hybrid_command(name="members", description="Quick member counts.")
    async def members(self, ctx: commands.Context):
        g = ctx.guild
        online = sum(1 for m in g.members if m.status != discord.Status.offline and not m.bot)
        container = v2.build(
            "info",
            "Members",
            fields=[
                ("Total", str(g.member_count)),
                ("Humans Online", str(online)),
                ("Bots", str(sum(1 for m in g.members if m.bot))),
            ],
        )
        await v2.send(ctx, container)

    @commands.hybrid_command(name="channels", description="List channels grouped by category.")
    async def channels(self, ctx: commands.Context):
        lines = []
        for cat in ctx.guild.categories:
            kids = ", ".join(f"#{c.name}" for c in cat.channels[:10])
            lines.append(f"**{cat.name}** — {kids or '—'}")
        loose = [
            c for c in ctx.guild.channels
            if c.category is None and isinstance(c, (discord.TextChannel, discord.VoiceChannel))
        ]
        if loose:
            lines.append("**Uncategorized** — " + ", ".join(f"#{c.name}" for c in loose[:10]))
        await v2.send(ctx, v2.info("Channels", "\n".join(lines)[:3900] or "No channels."))

    @commands.hybrid_command(name="avatar", description="Show a member's avatar.")
    async def avatar(self, ctx: commands.Context, member: discord.Member | None = None):
        m = member or ctx.author
        # For avatars, V1 embed works better since it supports large images natively.
        import discord as _d
        e = _d.Embed(title=f"Avatar — {m.display_name}", color=settings.accent_color)
        e.set_image(url=m.display_avatar.url)
        await ctx.send(embed=e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Insights(bot))
