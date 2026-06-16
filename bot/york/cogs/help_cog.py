"""Help command — interactive dropdown with V2 embeds."""
from __future__ import annotations

import discord
from discord.ext import commands

from .. import v2
from ..config import settings

CATEGORIES = {
    "Talk to York": (
        "How to start and stop conversations with York.",
        [
            ("Wake him up", "Say `Hey York` followed by anything, or `@York ...`."),
            ("Mention in passing", "Drop his name in a sentence — he will wait for the channel to quiet, then respond."),
            ("Stop him", "Say one of: **enough**, **done**, **set free**, **detach**, **goodbye**, **bye York**."),
            ("Per-user memory", "Each person has their own session, so multiple people can chat with him at once."),
        ],
    ),
    "Ask York for…": (
        "Things York can fetch or do mid-conversation.",
        [
            ("Real photos", "'Show me a picture of a red panda' -- he fetches a safe-for-work photo."),
            ("Reaction GIFs", "Ask for a hug, cheer, or facepalm and he will drop an anime reaction GIF."),
            ("Questions & advice", "Math, code explanations, opinions, recommendations — just ask."),
            ("Proactive ideas", "Sometimes he will volunteer a thought without being asked."),
        ],
    ),
    "Moderation": (
        "Server moderation tools. Requires appropriate permissions.",
        [
            ("Members", "`!kick`, `!ban`, `!unban`, `!mute <10m|2h|1d>`, `!unmute`, `!warn @user <reason>`"),
            ("Channels", "`!purge <n>`, `!slowmode <s>`, `!lock`, `!unlock`"),
            ("Roles", "`!addrole @user @role`, `!removerole @user @role`"),
            ("Warnings", "`!warnings @user`, `!delwarn @user <id>`, `!clearwarns @user`"),
        ],
    ),
    "Server Insights": (
        "Look around the server.",
        [
            ("Overview", "`!serverinfo`, `!members`, `!channels`"),
            ("People", "`!userinfo [@user]`, `!avatar [@user]`, `!banner [@user]`"),
            ("Roles", "`!roles` (interactive dropdown)"),
        ],
    ),
    "Social & Leveling": (
        "OwO-style social actions and chat XP.",
        [
            ("Reactions", "`!hug @user`, `!pet @user`, `!slap @user`, `!kiss @user`"),
            ("Reputation", "`!rep @user` (once every 22 hours)"),
            ("Profile", "`!profile [@user]`, `!leaderboard`"),
            ("Random", "`!roll [sides]`, `!8ball <question>`, `!say <text>`"),
        ],
    ),
    "Economy & Gambling": (
        "Earn, spend, rob, and gamble coins.",
        [
            ("Earn", "`!daily` (every ~22h), passive XP from chatting, level-up bonuses, `!fish`"),
            ("Send & Rob", "`!pay @user <amount|all>`, `!rob @user` (35% success · 5-min cooldown if caught)"),
            ("Fight", "`!fight @user` — challenge someone; random winner earns 50–500 coins"),
            ("Coinflip", "`!coinflip <bet> [heads|tails]` — double or nothing"),
            ("Gamble", "`!gamble <bet|all>` — random 50/50"),
            ("Slots", "`!slots <bet|all>` — spin 3 reels; payouts from 0.5× up to 20×"),
            ("Blackjack", "`!blackjack <bet|all>` — Hit / Stand / Double Down vs the dealer"),
            ("Horse Racing", "`!race <bet|all>` — pick a horse, watch the race live, win pays 2×"),
        ],
    ),
    "Shop & Inventory": (
        "Buy gifts and rings, open crates, sell loot.",
        [
            ("Browse", "`!shop` — see all items and prices"),
            ("Buy", "`!buy <item_id>` (e.g. `!buy ring_gold`)"),
            ("Inventory", "`!inventory [@user]`"),
            ("Sell loot", "`!sell <item_id> [qty]` · `!sell all` — sell all sellable items"),
            ("Crates", "`!fish` to catch crates · `!opencrate` to reveal what is inside"),
            ("Work", "`!work` — earn coins every 30 minutes"),
        ],
    ),
    "Starboard": (
        "Automatically highlights popular messages. Requires Manage Server to configure.",
        [
            ("Set channel", "`!starboard channel #channel` — where starred messages appear"),
            ("Set threshold", "`!starboard stars <n>` — how many reactions are needed"),
            ("Set emoji", "`!starboard emoji <emoji>` — which reaction triggers it (default ⭐)"),
            ("View config", "`!starboard` — show current settings"),
            ("Reset history", "`!starboard reset` — allow old messages to be starred again"),
        ],
    ),
    "Marriage": (
        "Find your person — or move on.",
        [
            ("Propose", "`!marry @user` — uses the fanciest ring in your inventory; they get a Yes/No prompt"),
            ("Check status", "`!marriage [@user]` — shows spouse, ring, and days together"),
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
        field_text = "\n\n".join(f"**{n}**\n{v}" for n, v in fields)
        container = v2.build(
            "info",
            f"{settings.emoji.info}  {cat}",
            desc,
            extra_sections=[(field_text, None)],
            footer=f"{settings.bot_name} · built by {settings.creator}",
        )
        await interaction.response.send_message(embed=container, ephemeral=True)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(HelpSelect())


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Show York's help menu.")
    async def help_cmd(self, ctx: commands.Context):
        container = v2.info(
            f"York — built by {settings.creator}",
            (
                "Your in-server Jarvis. I handle moderation, economy, leveling, "
                "fishing, marriage, AI conversation, and more.\n\n"
                "Select a category below to see what I can do."
            ),
        )
        await v2.send(ctx, container, view=HelpView())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
