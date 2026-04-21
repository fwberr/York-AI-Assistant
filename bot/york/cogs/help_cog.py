"""Help command — interactive dropdown."""
from __future__ import annotations

import discord
from discord.ext import commands

from .. import embeds
from ..config import settings

CATEGORIES = {
    "Talk to York": (
        "How to chat with York.",
        [
            ("Wake him", 'Say `Hey York` followed by anything.'),
            ("Mention him", '`@York how are you?`'),
            ("Stop him", "Say one of: **enough**, **done**, **set free**, **detach**, **goodbye**."),
            ("Buttons", "Every reply has *Detach* and *Suggest something* buttons."),
        ],
    ),
    "Moderation": (
        "Powers similar to Carlbot / Dyno / Wick.",
        [
            ("Members", "`!kick`, `!ban`, `!unban`, `!mute <10m|2h|1d>`, `!unmute`, `!warn`"),
            ("Channels", "`!purge <n>`, `!slowmode <s>`, `!lock`, `!unlock`"),
            ("Roles", "`!addrole @user @role`, `!removerole @user @role`"),
        ],
    ),
    "Server insights": (
        "Look around the server.",
        [
            ("Overview", "`!serverinfo`, `!members`, `!channels`"),
            ("People", "`!userinfo [@user]`, `!avatar [@user]`"),
            ("Roles", "`!roles` (interactive dropdown)"),
        ],
    ),
    "Fun (OwO style)": (
        "Social, economy, leveling.",
        [
            ("Social", "`!hug`, `!pet`, `!slap`, `!rep @user`"),
            ("Economy", "`!daily`, `!profile`, `!leaderboard`"),
            ("Random", "`!coinflip`, `!roll [sides]`, `!8ball <question>`, `!say <text>`"),
        ],
    ),
}


class HelpSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Pick a category…",
            options=[discord.SelectOption(label=name, value=name, emoji="◆") for name in CATEGORIES],
        )

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        desc, fields = CATEGORIES[cat]
        e = embeds.fields_embed(cat, [(n, v, False) for n, v in fields])
        e.description = desc
        await interaction.response.send_message(embed=e, ephemeral=True)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(HelpSelect())


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Show York's help menu.")
    async def help_cmd(self, ctx: commands.Context):
        e = embeds.info(
            f"I'm {settings.bot_name} — built by {settings.creator}.",
            (
                "Your in-server Jarvis. I learn how you talk, run moderation, surface "
                "insights, and sometimes I'll speak up on my own.\n\n"
                "Pick a category below to see what I can do."
            ),
        )
        await ctx.send(embed=e, view=HelpView())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
