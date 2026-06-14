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

from .. import v2
from ..config import settings

# Use DATA_DIR from settings so data persists across bot updates / redeployments.
PROFILES: Path = settings.data_dir / "profiles.json"
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
        "hugs_given": 0, "pets_given": 0, "slaps_given": 0, "kisses_given": 0,
    })


def _xp_for_next(level: int) -> int:
    return 25 * (level ** 2) + 250 * level + 500


def _grant_xp(p: dict, amount: int) -> tuple[bool, int, int]:
    p["xp"] += amount
    leveled = False
    coin_bonus = 0
    needed = _xp_for_next(p["level"])
    while p["xp"] >= needed:
        p["xp"] -= needed
        p["level"] += 1
        leveled = True
        bonus = 25 * p["level"]
        p["coins"] += bonus
        coin_bonus += bonus
        needed = _xp_for_next(p["level"])
    return leveled, p["level"], coin_bonus


GIF_CATEGORIES: set[str] = {
    "baka", "bite", "blush", "bored", "cry", "cuddle", "dance", "facepalm",
    "feed", "handhold", "happy", "highfive", "hug", "kick", "kiss", "laugh",
    "nod", "nom", "nope", "pat", "peck", "poke", "pout", "punch", "run",
    "shoot", "shrug", "sleep", "slap", "smile", "smug", "stare", "think",
    "thumbsup", "tickle", "wave", "wink", "yawn", "yeet",
}
_GIF_ALIAS = {"pet": "pat"}


async def fetch_gif(action: str) -> str | None:
    cat = _GIF_ALIAS.get(action.lower(), action.lower())
    if cat not in GIF_CATEGORIES:
        return None
    url = f"https://nekos.best/api/v2/{cat}"
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


_fetch_gif = fetch_gif


async def fetch_image(query: str) -> str | None:
    q = (query or "").strip()
    if not q:
        return None
    url = "https://api.openverse.org/v1/images/"
    params = {"q": q, "page_size": 10, "mature": "false", "license_type": "all"}
    headers = {"User-Agent": "YorkDiscordBot/1.0 (+https://replit.com)"}
    try:
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                results = data.get("results") or []
                ok = [
                    x for x in results
                    if (x.get("url") or "").lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))
                    and not x.get("mature", False)
                ]
                pool = ok or results
                if not pool:
                    return None
                pick = random.choice(pool[:5])
                return pick.get("url") or pick.get("thumbnail")
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

    async def _social(self, ctx, target, action, verb_self, verb_other, key):
        d = _load(); p = _profile(d, ctx.author.id); p[key] = p.get(key, 0) + 1
        leveled, lvl, bonus = _grant_xp(p, 5); _save(d)

        if target.id == ctx.author.id:
            desc = f"{ctx.author.mention} {verb_self}."
        else:
            desc = f"{ctx.author.mention} {verb_other} {target.mention}."

        footer_text = (
            f"Level up! Now level {lvl} (+{bonus} coins) · {settings.bot_name} · built by {settings.creator}"
            if leveled else
            f"{settings.bot_name} · built by {settings.creator}"
        )
        container = v2.build(
            "info",
            f"{settings.emoji.spark}  {action.title()}!",
            desc,
            footer=footer_text,
        )
        gif = await _fetch_gif(action)
        msg = await v2.send(ctx, container)
        if gif:
            await ctx.channel.send(gif)

    @commands.hybrid_command(name="hug", description="Hug a member.")
    async def hug(self, ctx, member: discord.Member):
        await self._social(ctx, member, "hug", "hugs themselves. Aww.", "hugs", "hugs_given")

    @commands.hybrid_command(name="pet", description="Pet a member.")
    async def pet(self, ctx, member: discord.Member):
        await self._social(ctx, member, "pet", "pats their own head.", "pets", "pets_given")

    @commands.hybrid_command(name="slap", description="Slap a member.")
    async def slap(self, ctx, member: discord.Member):
        await self._social(ctx, member, "slap", "slapped themselves. Why.", "slaps", "slaps_given")

    @commands.hybrid_command(name="kiss", description="Kiss a member.")
    async def kiss(self, ctx, member: discord.Member):
        await self._social(ctx, member, "kiss", "blows themselves a kiss.", "kisses", "kisses_given")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if not (message.content or "").strip():
            return
        if message.content.startswith("!"):
            return

        d = _load(); p = _profile(d, message.author.id)
        now = time.time()
        if now - p.get("last_chat_xp", 0) < 60:
            return
        p["last_chat_xp"] = now

        gained = random.randint(8, 18)
        leveled, lvl, bonus = _grant_xp(p, gained)
        p["coins"] += 1 + (lvl // 5)
        _save(d)

        if leveled:
            try:
                await message.channel.send(embed=v2.success(
                    f"{settings.emoji.spark}  Level Up!",
                    f"{message.author.mention} reached **level {lvl}** and earned **{bonus}** bonus coins.",
                ))
            except discord.HTTPException:
                pass

    @commands.hybrid_command(name="daily", description="Claim your daily coins.")
    async def daily(self, ctx):
        d = _load(); p = _profile(d, ctx.author.id)
        now = time.time()
        if now - p["last_daily"] < 22 * 3600:
            remaining = int(22 * 3600 - (now - p["last_daily"]))
            await v2.send(ctx, v2.warn(
                "Already Claimed",
                f"Your next daily is available in **{remaining//3600}h {remaining%3600//60}m**.",
            ))
            return
        amount = random.randint(80, 240)
        p["coins"] += amount; p["last_daily"] = now
        _grant_xp(p, 15); _save(d)
        await v2.send(ctx, v2.success(
            "Daily Reward Claimed",
            f"You received **{amount}** coins.\nNew balance: **{p['coins']}** coins.",
        ))

    @commands.hybrid_command(name="rep", description="Give a reputation point to someone.")
    async def rep(self, ctx, member: discord.Member):
        if member.id == ctx.author.id:
            await v2.send(ctx, v2.warn("Not Allowed", "You cannot give reputation to yourself."))
            return
        d = _load(); giver = _profile(d, ctx.author.id); recv = _profile(d, member.id)
        now = time.time()
        if now - giver["last_rep"] < 22 * 3600:
            remaining = int(22 * 3600 - (now - giver["last_rep"]))
            await v2.send(ctx, v2.warn(
                "Wait a Bit",
                f"You can give reputation again in **{remaining//3600}h {remaining%3600//60}m**.",
            ))
            return
        recv["rep"] += 1; giver["last_rep"] = now; _save(d)
        await v2.send(ctx, v2.success(
            "Reputation Given",
            f"{member.mention} now has **{recv['rep']}** reputation.",
            thumbnail_url=member.display_avatar.url,
        ))

    @commands.hybrid_command(name="profile", description="Show your or someone's profile.")
    async def profile(self, ctx, member: discord.Member | None = None):
        m = member or ctx.author
        d = _load(); p = _profile(d, m.id); _save(d)
        married_to = p.get("married_to")
        marriage_line = ""
        if married_to:
            spouse = ctx.guild.get_member(int(married_to)) if ctx.guild else None
            spouse_name = spouse.display_name if spouse else f"User {married_to}"
            ring = p.get("ring", "")
            marriage_line = f"\n💍 Married to **{spouse_name}**" + (f" with a {ring.replace('_', ' ').title()}" if ring else "")

        container = v2.build(
            "info",
            f"{settings.emoji.member}  {m.display_name}",
            f"Level **{p['level']}** · {p['xp']}/{_xp_for_next(p['level'])} XP{marriage_line}",
            fields=[
                ("Coins", f"{p.get('coins', 0):,}"),
                ("Reputation", str(p.get("rep", 0))),
                ("Hugs Given", str(p.get("hugs_given", 0))),
                ("Pets Given", str(p.get("pets_given", 0))),
                ("Slaps Given", str(p.get("slaps_given", 0))),
                ("Kisses Given", str(p.get("kisses_given", 0))),
            ],
            thumbnail_url=m.display_avatar.url,
        )
        await v2.send(ctx, container)

    @commands.hybrid_command(name="leaderboard", description="Top members by level.")
    async def leaderboard(self, ctx):
        d = _load()
        rows = sorted(d.items(), key=lambda kv: (kv[1].get("level", 1), kv[1].get("xp", 0)), reverse=True)[:10]
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, p) in enumerate(rows, start=1):
            user = ctx.guild.get_member(int(uid))
            name = user.display_name if user else f"User {uid}"
            medal = medals[i - 1] if i <= 3 else f"`#{i:>2}`"
            lines.append(f"{medal} **{name}** — Lvl {p.get('level', 1)} · {p.get('coins', 0):,} coins")
        await v2.send(ctx, v2.info("Leaderboard", "\n".join(lines) or "No data yet."))

    @commands.hybrid_command(name="coinflip", description="Flip a coin. Optionally bet coins.")
    @app_commands.describe(bet="Coins to wager (or 'all').", side="heads or tails")
    async def coinflip(self, ctx: commands.Context, bet: str | None = None, side: str | None = None):
        if bet is None:
            result = random.choice(["Heads", "Tails"])
            await v2.send(ctx, v2.info("Coinflip", f"The coin landed on **{result}**."))
            return

        d = _load(); p = _profile(d, ctx.author.id)
        balance = p.get("coins", 0)
        bet_l = bet.strip().lower()
        if bet_l in ("all", "max"):
            amount = balance
        else:
            try:
                amount = int(bet_l)
            except ValueError:
                await v2.send(ctx, v2.danger("Bad Bet", "Bet must be a number or `all`."))
                return

        if amount <= 0:
            await v2.send(ctx, v2.danger("Bad Bet", "Bet must be positive."))
            return
        if amount > balance:
            await v2.send(ctx, v2.danger("Not Enough Coins", f"You only have **{balance:,}** coins."))
            return

        side_l = (side or "").strip().lower()
        if side_l in ("h", "head", "heads"):
            choice = "heads"
        elif side_l in ("t", "tail", "tails"):
            choice = "tails"
        elif side_l == "":
            choice = random.choice(["heads", "tails"])
        else:
            await v2.send(ctx, v2.danger("Bad Side", "Pick `heads` or `tails`."))
            return

        result = random.choice(["heads", "tails"])
        won = result == choice

        if won:
            p["coins"] = balance + amount
            _grant_xp(p, 5); _save(d)
            await v2.send(ctx, v2.success(
                f"{settings.emoji.spark}  {result.title()} — You Win!",
                f"You called **{choice}** and doubled your bet.\n"
                f"**+{amount:,}** coins · New balance: **{p['coins']:,}**",
            ))
        else:
            p["coins"] = balance - amount; _save(d)
            await v2.send(ctx, v2.danger(
                f"{result.title()} — You Lose.",
                f"You called **{choice}** — the coin disagreed.\n"
                f"**−{amount:,}** coins · New balance: **{p['coins']:,}**",
            ))

    @commands.hybrid_command(name="gamble", description="Pure 50/50: bet coins, win double or lose it all.")
    @app_commands.describe(bet="Coins to wager (or 'all').")
    async def gamble(self, ctx: commands.Context, bet: str):
        await self.coinflip(ctx, bet=bet, side=None)

    @commands.hybrid_command(name="roll", description="Roll a dice (default d20).")
    async def roll(self, ctx, sides: int = 20):
        sides = max(2, min(1000, sides))
        await v2.send(ctx, v2.info(f"Rolled d{sides}", f"You rolled a **{random.randint(1, sides)}**."))

    @commands.hybrid_command(name="8ball", description="Ask the magic 8-ball.")
    async def eightball(self, ctx, *, question: str):
        await v2.send(ctx, v2.info(
            "Magic 8-Ball",
            f"**Question:** {question}\n**Answer:** {random.choice(_8BALL)}",
        ))

    @commands.hybrid_command(name="say", description="Make York say something.")
    async def say(self, ctx, *, message: str):
        await v2.send(ctx, v2.info("York", message))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun(bot))
