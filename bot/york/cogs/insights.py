"""Server insights — info, members, roles, channels, user lookup."""
from __future__ import annotations

from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from .. import embeds
from ..config import settings


class RoleSelect(discord.ui.Select):
    def __init__(self, roles: List[discord.Role]):
        options = [
            discord.SelectOption(
                label=r.name[:90],
                value=str(r.id),
                description=f"{len(r.members)} members · pos {r.position}"[:90],
            )
            for r in roles[:25]
        ]
        super().__init__(placeholder="Inspect a role…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        if not role:
            await interaction.response.send_message("Role vanished.", ephemeral=True)
            return
        e = embeds.fields_embed(
            f"Role · {role.name}",
            [
                ("Members", str(len(role.members)), True),
                ("Color", str(role.color), True),
                ("Hoisted", "yes" if role.hoist else "no", True),
                ("Mentionable", "yes" if role.mentionable else "no", True),
                ("Position", str(role.position), True),
                ("Created", discord.utils.format_dt(role.created_at, "R"), True),
            ],
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


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
        e = embeds.fields_embed(
            f"{settings.emoji.crown}  {g.name}",
            [
                ("Members", f"{g.member_count} ({humans} humans · {bots} bots)", True),
                ("Channels", f"{len(g.text_channels)} text · {len(g.voice_channels)} voice", True),
                ("Roles", str(len(g.roles)), True),
                ("Owner", g.owner.mention if g.owner else "—", True),
                ("Boosts", f"Lvl {g.premium_tier} · {g.premium_subscription_count} boosts", True),
                ("Created", discord.utils.format_dt(g.created_at, "R"), True),
            ],
        )
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="userinfo", description="Show details about a member.")
    async def userinfo(self, ctx: commands.Context, member: discord.Member | None = None):
        m = member or ctx.author
        roles = ", ".join(r.mention for r in reversed(m.roles[1:])) or "—"
        e = embeds.fields_embed(
            f"{settings.emoji.member}  {m.display_name}",
            [
                ("Tag", str(m), True),
                ("ID", str(m.id), True),
                ("Bot", "yes" if m.bot else "no", True),
                ("Joined server", discord.utils.format_dt(m.joined_at, "R") if m.joined_at else "—", True),
                ("Account created", discord.utils.format_dt(m.created_at, "R"), True),
                ("Top role", m.top_role.mention, True),
                (f"Roles ({len(m.roles)-1})", roles[:1024], False),
            ],
        )
        e.set_thumbnail(url=m.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="roles", description="List server roles (interactive).")
    async def roles(self, ctx: commands.Context):
        roles = sorted([r for r in ctx.guild.roles if not r.is_default()], key=lambda r: -r.position)
        if not roles:
            await ctx.send(embed=embeds.info("Roles", "No custom roles."))
            return
        preview = "\n".join(f"{settings.emoji.role} {r.mention} — {len(r.members)} members" for r in roles[:15])
        more = f"\n…and {len(roles)-15} more" if len(roles) > 15 else ""
        await ctx.send(embed=embeds.info("Roles", preview + more), view=RoleView(roles))

    @commands.hybrid_command(name="members", description="Quick member counts.")
    async def members(self, ctx: commands.Context):
        g = ctx.guild
        online = sum(1 for m in g.members if m.status != discord.Status.offline and not m.bot)
        await ctx.send(embed=embeds.fields_embed(
            "Members",
            [
                ("Total", str(g.member_count), True),
                ("Online (humans)", str(online), True),
                ("Bots", str(sum(1 for m in g.members if m.bot)), True),
            ],
        ))

    @commands.hybrid_command(name="channels", description="List channels grouped by category.")
    async def channels(self, ctx: commands.Context):
        lines = []
        for cat in ctx.guild.categories:
            kids = ", ".join(f"#{c.name}" for c in cat.channels[:10])
            lines.append(f"**{cat.name}** — {kids or '—'}")
        loose = [c for c in ctx.guild.channels if c.category is None and isinstance(c, (discord.TextChannel, discord.VoiceChannel))]
        if loose:
            lines.append("**Uncategorized** — " + ", ".join(f"#{c.name}" for c in loose[:10]))
        await ctx.send(embed=embeds.info("Channels", "\n".join(lines)[:4000] or "No channels."))

    @commands.hybrid_command(name="avatar", description="Show a member's avatar.")
    async def avatar(self, ctx: commands.Context, member: discord.Member | None = None):
        m = member or ctx.author
        e = embeds.info(f"Avatar — {m.display_name}")
        e.set_image(url=m.display_avatar.url)
        await ctx.send(embed=e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Insights(bot))
