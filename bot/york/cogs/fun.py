"""OwO-style fun commands — pet, hug, slap, rep, daily, profile, coinflip, 8ball."""
from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from .. import embeds
from ..config import settings

PROFILES = Path("bot/data/profiles.json")
PROFILES.parent.mkdir(parents=True, exist_ok=True)


def _load() -> Dict[str, dict]:
    if PROFILES.exists():
        try:
            return json.loads(PROFILES.read_text())
        except Exception:
            return {}
    return {}


def _save(d: Dict[str, dict]) -> None:
    PROFILES.write_text(json.dumps(d, indent=2))


def _profile(d: Dict[str, dict], uid: int) -> dict:
    return d.setdefault(str(uid), {
        "coins": 0, "rep": 0, "xp": 0, "level": 1,
        "last_daily": 0, "last_rep": 0, "last_chat_xp": 0,
        "hugs_given": 0, "pets_given": 0, "slaps_given": 0,
    })


def _grant_xp(p: dict, amount: int) -> tuple[bool, int, int]:
    """Add XP, auto-leveling. Returns (did_level, new_level, coin_bonus)."""
    p["xp"] += amount
    leveled = False
    coin_bonus = 0
    while p["xp"] >= p["level"] * 100:
        p["xp"] -= p["level"] * 100
        p["level"] += 1
        leveled = True
        # Reward: more coins the higher your level.
        bonus = 25 * p["level"]
        p["coins"] += bonus
        coin_bonus += bonus
    return leveled, p["level"], coin_bonus


# Anime-style SFW reaction GIF endpoints. nekos.best is a public API
# with curated SFW content — no auth, no NSFW endpoints exposed here.
_GIF_ENDPOINTS = {
    "hug":  "https://nekos.best/api/v2/hug",
    "pet":  "https://nekos.best/api/v2/pat",
    "slap": "https://nekos.best/api/v2/slap",
}


async def _fetch_gif(action: str) -> str | None:
    url = _GIF_ENDPOINTS.get(action)
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                results = data.get("results") or []
                if not results:
                    return None
                return results[0].get("url")
    except Exception:
        return None


_8BALL = [
    "It is certain.", "Without a doubt.", "Most likely.", "Outlook good.",
    "Signs point to yes.", "Reply hazy, try again.", "Ask again later.",
    "Better not tell you now.", "Don't count on it.", "My sources say no.",
    "Outlook not so good.", "Very doubtful.",
]


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- social actions --------
    async def _social(
        self,
        ctx: commands.Context,
        target: discord.Member,
        action: str,
        verb_self: str,
        verb_other: str,
        key: str,
    ):
        d = _load(); p = _profile(d, ctx.author.id); p[key] = p.get(key, 0) + 1
        leveled, lvl, bonus = _grant_xp(p, 5); _save(d)

        if target.id == ctx.author.id:
            desc = f"{ctx.author.mention} {verb_self}."
        else:
            desc = f"{ctx.author.mention} {verb_other} {target.mention}."

        e = embeds.info(f"{settings.emoji.spark}  {action.title()}!", desc)
        gif = await _fetch_gif(action)
        if gif:
            e.set_image(url=gif)
        if leveled:
            e.set_footer(
                text=f"Level up! You are now level {lvl} (+{bonus} coins) · "
                     f"{settings.bot_name} · built by {settings.creator}"
            )
        await ctx.send(embed=e)

    @commands.hybrid_command(name="hug", description="Hug a member (with a random anime GIF).")
    async def hug(self, ctx, member: discord.Member):
        await self._social(ctx, member, "hug", "hugs themselves. Aww.", "hugs", "hugs_given")

    @commands.hybrid_command(name="pet", description="Pet a member (with a random anime GIF).")
    async def pet(self, ctx, member: discord.Member):
        await self._social(ctx, member, "pet", "pats their own head.", "pets", "pets_given")

    @commands.hybrid_command(name="slap", description="Slap a member (with a random anime GIF).")
    async def slap(self, ctx, member: discord.Member):
        await self._social(ctx, member, "slap", "slapped themselves. Why.", "slaps", "slaps_given")

    # -------- passive chat XP --------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Award XP for chatting in the server. 60s cooldown per user
        to keep spam-farming in check. Higher levels = bigger coin payouts
        on level-up (handled in _grant_xp)."""
        if message.author.bot or not message.guild:
            return
        if not (message.content or "").strip():
            return
        # Don't award XP for bot commands themselves.
        if message.content.startswith("!"):
            return

        d = _load(); p = _profile(d, message.author.id)
        now = time.time()
        if now - p.get("last_chat_xp", 0) < 60:
            return
        p["last_chat_xp"] = now

        gained = random.randint(8, 18)
        leveled, lvl, bonus = _grant_xp(p, gained)
        # Small per-message coin trickle that scales with level.
        p["coins"] += 1 + (lvl // 5)
        _save(d)

        if leveled:
            try:
                await message.channel.send(
                    embed=embeds.success(
                        f"{settings.emoji.spark} Level up!",
                        f"{message.author.mention} reached **level {lvl}** "
                        f"and earned **{bonus}** bonus coins.",
                    )
                )
            except discord.HTTPException:
                pass

    # -------- economy / rep --------
    @commands.hybrid_command(name="daily", description="Claim your daily coins.")
    async def daily(self, ctx):
        d = _load(); p = _profile(d, ctx.author.id)
        now = time.time()
        if now - p["last_daily"] < 22 * 3600:
            remaining = int(22 * 3600 - (now - p["last_daily"]))
            await ctx.send(embed=embeds.warn("Already claimed", f"Try again in {remaining//3600}h {remaining%3600//60}m."))
            return
        amount = random.randint(80, 240)
        p["coins"] += amount; p["last_daily"] = now
        _grant_xp(p, 15); _save(d)
        await ctx.send(embed=embeds.success("Daily claimed", f"You picked up **{amount}** coins. Balance: **{p['coins']}**."))

    @commands.hybrid_command(name="rep", description="Give a reputation point to someone.")
    async def rep(self, ctx, member: discord.Member):
        if member.id == ctx.author.id:
            await ctx.send(embed=embeds.warn("Nope", "You can't rep yourself."))
            return
        d = _load(); giver = _profile(d, ctx.author.id); recv = _profile(d, member.id)
        now = time.time()
        if now - giver["last_rep"] < 22 * 3600:
            remaining = int(22 * 3600 - (now - giver["last_rep"]))
            await ctx.send(embed=embeds.warn("Wait a bit", f"Next rep in {remaining//3600}h {remaining%3600//60}m."))
            return
        recv["rep"] += 1; giver["last_rep"] = now
        _save(d)
        await ctx.send(embed=embeds.success("Rep given", f"{member.mention} now has **{recv['rep']}** rep."))

    @commands.hybrid_command(name="profile", description="Show your or someone's profile.")
    async def profile(self, ctx, member: discord.Member | None = None):
        m = member or ctx.author
        d = _load(); p = _profile(d, m.id); _save(d)
        e = embeds.fields_embed(
            f"{settings.emoji.member}  {m.display_name}",
            [
                ("Level", str(p["level"]), True),
                ("XP", f"{p['xp']} / {p['level']*100}", True),
                ("Coins", str(p["coins"]), True),
                ("Reputation", str(p["rep"]), True),
                ("Hugs given", str(p.get("hugs_given", 0)), True),
                ("Pets given", str(p.get("pets_given", 0)), True),
            ],
        )
        e.set_thumbnail(url=m.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="leaderboard", description="Top members by level.")
    async def leaderboard(self, ctx):
        d = _load()
        rows = sorted(d.items(), key=lambda kv: (kv[1].get("level", 1), kv[1].get("xp", 0)), reverse=True)[:10]
        lines = []
        for i, (uid, p) in enumerate(rows, start=1):
            user = ctx.guild.get_member(int(uid))
            name = user.display_name if user else f"User {uid}"
            lines.append(f"`#{i:>2}` **{name}** — Lvl {p.get('level',1)} · {p.get('coins',0)} coins")
        await ctx.send(embed=embeds.info("Leaderboard", "\n".join(lines) or "No data yet."))

    # -------- gambling --------
    @commands.hybrid_command(
        name="coinflip",
        description="Flip a coin. Optionally bet coins: double or lose it all.",
    )
    @app_commands.describe(
        bet="Coins to wager (or 'all'). Win = double, lose = gone.",
        side="Your call: heads or tails.",
    )
    async def coinflip(self, ctx: commands.Context, bet: str | None = None, side: str | None = None):
        # Free flip — no args.
        if bet is None:
            await ctx.send(embed=embeds.info("Coinflip", random.choice(["**Heads**", "**Tails**"])))
            return

        d = _load(); p = _profile(d, ctx.author.id)
        balance = p.get("coins", 0)

        # Parse the wager.
        bet_l = bet.strip().lower()
        if bet_l in ("all", "max"):
            amount = balance
        else:
            try:
                amount = int(bet_l)
            except ValueError:
                await ctx.send(embed=embeds.danger("Bad bet", "Bet must be a number or `all`."))
                return

        if amount <= 0:
            await ctx.send(embed=embeds.danger("Bad bet", "Bet must be positive."))
            return
        if amount > balance:
            await ctx.send(embed=embeds.danger(
                "Not enough coins",
                f"You only have **{balance}** coins. Earn more with `!daily`.",
            ))
            return

        # Pick a side (random if not specified).
        side_l = (side or "").strip().lower()
        if side_l in ("h", "head", "heads"):
            choice = "heads"
        elif side_l in ("t", "tail", "tails"):
            choice = "tails"
        elif side_l == "":
            choice = random.choice(["heads", "tails"])
        else:
            await ctx.send(embed=embeds.danger("Bad side", "Pick `heads` or `tails` (or leave blank)."))
            return

        result = random.choice(["heads", "tails"])
        won = result == choice

        if won:
            p["coins"] = balance + amount
            _grant_xp(p, 5); _save(d)
            e = embeds.success(
                f"{settings.emoji.spark} It's {result.title()} — you win!",
                f"You called **{choice}** and doubled your bet.\n"
                f"**+{amount}** coins · new balance: **{p['coins']}**",
            )
        else:
            p["coins"] = balance - amount
            _save(d)
            e = embeds.danger(
                f"It's {result.title()} — you lose.",
                f"You called **{choice}**. Coin disagreed.\n"
                f"**−{amount}** coins · new balance: **{p['coins']}**",
            )
        await ctx.send(embed=e)

    @commands.hybrid_command(name="gamble", description="Pure 50/50: bet coins, win double or lose it all.")
    @app_commands.describe(bet="Coins to wager (or 'all').")
    async def gamble(self, ctx: commands.Context, bet: str):
        # Same mechanics as coinflip but always random side.
        await self.coinflip(ctx, bet=bet, side=None)

    @commands.hybrid_command(name="roll", description="Roll a dice (default d20).")
    async def roll(self, ctx, sides: int = 20):
        sides = max(2, min(1000, sides))
        await ctx.send(embed=embeds.info(f"Rolled d{sides}", f"**{random.randint(1, sides)}**"))

    @commands.hybrid_command(name="8ball", description="Ask the magic 8-ball.")
    async def eightball(self, ctx, *, question: str):
        await ctx.send(embed=embeds.info("Magic 8-ball", f"**Q:** {question}\n**A:** {random.choice(_8BALL)}"))

    @commands.hybrid_command(name="say", description="Make York say something in an embed.")
    async def say(self, ctx, *, message: str):
        await ctx.send(embed=embeds.info("York", message))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun(bot))
