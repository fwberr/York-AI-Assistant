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
            ("Wake him", "Say `Hey York` followed by anything, or `@York ...`."),
            ("Mention in passing", "Drop his name in a sentence — he'll wait for the chat to quiet, then chime in."),
            ("Stop him", "Say one of: **enough**, **done**, **set free**, **detach**, **goodbye**."),
            ("Per-user memory", "Each person has their own session, so multiple people can chat with him at once."),
        ],
    ),
    "Ask York for…": (
        "Things York can do mid-conversation, just by asking.",
        [
            ("Real photos", "“Show me a picture of a red panda” → he sends a safe-for-work photo."),
            ("Reaction GIFs", "Ask for a hug / cheer / facepalm / etc. and he'll drop an anime reaction GIF."),
            ("Questions & advice", "Math, code, explanations, opinions, recommendations — just ask."),
            ("Style mirroring", "He learns how you talk over time and matches your vibe."),
            ("Proactive ideas", "Sometimes he'll volunteer a thought without being asked."),
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
    "Social & leveling": (
        "OwO-style social actions and chat XP.",
        [
            ("Reactions", "`!hug @user`, `!pet @user`, `!slap @user`, `!kiss @user`"),
            ("Reputation", "`!rep @user` (once every 22h)"),
            ("Profile", "`!profile [@user]`, `!leaderboard`"),
            ("Random", "`!roll [sides]`, `!8ball <question>`, `!say <text>`"),
        ],
    ),
    "Economy & gambling": (
        "Earn, spend, send and gamble coins.",
        [
            ("Earn", "`!daily` (every ~22h), passive XP from chatting, level-up bonuses"),
            ("Send coins", "`!pay @user <amount|all>`"),
            ("Coinflip", "`!coinflip <bet> [heads|tails]` — double or nothing"),
            ("Pure gamble", "`!gamble <bet|all>` — random 50/50"),
            ("Blackjack", "`!blackjack <bet|all>` — interactive Hit / Stand / Double vs the dealer"),
        ],
    ),
    "Shop & inventory": (
        "Buy gifts, trinkets and rings.",
        [
            ("Browse", "`!shop` — see all items and prices"),
            ("Buy", "`!buy <item_id>` (e.g. `!buy ring_gold`)"),
            ("Inventory", "`!inventory [@user]`"),
            ("Catalog", "9 ring tiers (Copper → Celestial Halo) plus roses, chocolates, teddy, crown, yacht."),
        ],
    ),
    "Marriage": (
        "Find your person — or break up.",
        [
            ("Propose", "`!marry @user` — uses the fanciest ring in your inventory; they get a Yes/No prompt"),
            ("Check status", "`!marriage [@user]` — shows spouse, ring used, and days together"),
            ("End it", "`!divorce` — clears the marriage on both sides"),
        ],
    ),
}


class HelpSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Pick a category…",
            options=[discord.SelectOption(label=name, value=name) for name in CATEGORIES],
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
