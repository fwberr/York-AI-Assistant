"""Fishing & Work cogs — !fish, !opencrate, !work."""
from __future__ import annotations

import random
import time

import discord
from discord.ext import commands

from .. import v2
from ..config import settings
from .fun import _load, _save, _profile, _grant_xp
from .economy import SELLABLE_ITEMS, _CRATE_KEYS, _CRATE_WEIGHTS

_RARITY_COLORS = {
    "common":    "info",
    "uncommon":  "info",
    "rare":      "success",
    "epic":      "warn",
    "legendary": "danger",
}

_RARITY_LABELS = {
    "common":    "Common",
    "uncommon":  "Uncommon",
    "rare":      "🌟 Rare",
    "epic":      "💜 Epic",
    "legendary": "🌈 Legendary",
}

_FISH_POOL = [
    ("a tiny minnow",    5,   60),
    ("a scrappy carp",   15,  50),
    ("a decent bass",    30,  30),
    ("a fat catfish",    60,  20),
    ("a prize trout",    120, 10),
    ("a massive salmon", 250, 5),
]
_FISH_NAMES   = [x[0] for x in _FISH_POOL]
_FISH_COINS   = [x[1] for x in _FISH_POOL]
_FISH_WEIGHTS = [x[2] for x in _FISH_POOL]

FISHING_COOLDOWN = 3 * 60   # 3 minutes
WORK_COOLDOWN    = 30 * 60  # 30 minutes

# Flavour text for !work — randomly picked each shift.
_WORK_SHIFTS = [
    ("delivered packages across the city",         (80,  160)),
    ("worked a shift at the coffee shop",           (70,  140)),
    ("fixed a server rack in the data centre",      (100, 200)),
    ("wrote code for a client all afternoon",       (90,  180)),
    ("drove an Uber around town",                   (60,  130)),
    ("stocked shelves at the supermarket",          (50,  110)),
    ("tutored a student in mathematics",            (80,  160)),
    ("helped moderate a Discord server",            (70,  150)),
    ("repaired a broken fence for a neighbour",     (60,  120)),
    ("sold handmade crafts at the weekend market",  (75,  175)),
    ("walked five dogs around the park",            (55,  105)),
    ("recorded a podcast episode for a client",     (90,  190)),
]


class Fishing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- fish ----------
    @commands.hybrid_command(name="fish", description="Go fishing! 3-minute cooldown.")
    async def fish(self, ctx: commands.Context):
        d = _load(); p = _profile(d, ctx.author.id)
        now = time.time()
        last = p.get("last_fish", 0)
        if now - last < FISHING_COOLDOWN:
            remaining = int(FISHING_COOLDOWN - (now - last))
            await v2.send(ctx, v2.warn(
                "Line Already Cast",
                f"Your line is still in the water. Try again in **{remaining // 60}m {remaining % 60}s**.",
            ))
            return

        p["last_fish"] = now
        _grant_xp(p, random.randint(3, 8))

        if random.random() < 0.25:
            inv = p.setdefault("inventory", [])
            inv.append("crate")
            _save(d)
            await v2.send(ctx, v2.success(
                f"{settings.emoji.crate}  Mystery Crate!",
                f"You reeled in a **Mystery Crate** instead of a fish!\n"
                f"Use `!opencrate` to see what's inside.",
            ))
        else:
            name = random.choices(_FISH_NAMES, weights=_FISH_WEIGHTS, k=1)[0]
            idx = _FISH_NAMES.index(name)
            coins = max(1, _FISH_COINS[idx] + random.randint(-5, 10))
            p["coins"] = p.get("coins", 0) + coins
            _save(d)
            await v2.send(ctx, v2.success(
                f"{settings.emoji.fish}  Catch!",
                f"You caught **{name}** and sold it for **{coins}** coins.\n"
                f"Balance: **{p['coins']:,}** coins.",
            ))

    # ---------- opencrate ----------
    @commands.hybrid_command(name="opencrate", description="Open a Mystery Crate from your inventory.")
    async def opencrate(self, ctx: commands.Context):
        d = _load(); p = _profile(d, ctx.author.id)
        inv: list[str] = p.get("inventory", [])

        if "crate" not in inv:
            await v2.send(ctx, v2.warn(
                "No Crates",
                "You have no Mystery Crates. Go `!fish` to find one!",
            ))
            return

        inv.remove("crate")
        loot_id: str | None = random.choices(_CRATE_KEYS, weights=_CRATE_WEIGHTS, k=1)[0]

        if loot_id is None:
            _save(d)
            await v2.send(ctx, v2.warn(
                f"{settings.emoji.crate}  Empty Crate",
                "You cracked it open and found… nothing. Better luck next time.",
            ))
            return

        item = SELLABLE_ITEMS[loot_id]
        inv.append(loot_id)
        _save(d)

        style = _RARITY_COLORS.get(item["rarity"], "info")
        rarity_label = _RARITY_LABELS.get(item["rarity"], item["rarity"].title())

        await v2.send(ctx, v2.build(
            style,
            f"{settings.emoji.crate}  Crate Opened!",
            "You found something inside!",
            fields=[
                ("Item",        item["name"]),
                ("Rarity",      rarity_label),
                ("Sell Value",  f"{item['sell']:,} coins" if item["sell"] > 0 else "Worthless junk"),
                ("Description", item["desc"]),
            ],
            footer=f"Sell it with !sell {loot_id} · {settings.bot_name} · built by {settings.creator}",
        ))

    # ---------- work ----------
    @commands.hybrid_command(name="work", description="Work a shift and earn coins. 30-minute cooldown.")
    async def work(self, ctx: commands.Context):
        d = _load(); p = _profile(d, ctx.author.id)
        now = time.time()
        last = p.get("last_work", 0)
        if now - last < WORK_COOLDOWN:
            remaining = int(WORK_COOLDOWN - (now - last))
            await v2.send(ctx, v2.warn(
                "Still On Break",
                f"You need to rest before your next shift.\n"
                f"Available again in **{remaining // 60}m {remaining % 60}s**.",
            ))
            return

        shift, (low, high) = random.choice(_WORK_SHIFTS)
        # Bonus scales slightly with level so higher-level players earn a bit more.
        level_bonus = p.get("level", 1) * 2
        earned = random.randint(low, high) + level_bonus
        p["coins"] = p.get("coins", 0) + earned
        p["last_work"] = now
        _grant_xp(p, random.randint(10, 20))
        _save(d)

        await v2.send(ctx, v2.success(
            f"Shift Complete",
            f"You {shift} and earned **{earned:,}** coins.\n"
            f"Balance: **{p['coins']:,}** coins.",
            footer=f"Next shift available in 30 minutes · {settings.bot_name} · built by {settings.creator}",
        ))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fishing(bot))
