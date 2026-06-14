"""Fishing cog — !fish, !opencrate.

Fish → earn coins directly OR get a mystery crate.
Crates → open with !opencrate to get (or not get) a random sellable item.
Sell loot items with !sell <item_id> (defined in economy.py).
"""
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

# Fish-only loot table (coins earned directly, no crate)
_FISH_POOL = [
    ("a tiny minnow",    5,   60),
    ("a scrappy carp",   15,  50),
    ("a decent bass",    30,  30),
    ("a fat catfish",    60,  20),
    ("a prize trout",    120, 10),
    ("a massive salmon", 250, 5),
]
_FISH_NAMES = [x[0] for x in _FISH_POOL]
_FISH_COINS = [x[1] for x in _FISH_POOL]
_FISH_WEIGHTS = [x[2] for x in _FISH_POOL]

FISHING_COOLDOWN = 3 * 60  # 3 minutes


class Fishing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="fish", description="Go fishing! 3-minute cooldown. May reel in coins or a mystery crate.")
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

        # 25% crate, 75% direct fish
        if random.random() < 0.25:
            inv = p.setdefault("inventory", [])
            inv.append("crate")
            _save(d)
            await v2.send(ctx, v2.success(
                f"{settings.emoji.crate}  Mystery Crate!",
                f"You reeled in a **Mystery Crate** instead of a fish!\n"
                f"Use `!opencrate` to open it and see what's inside.",
            ))
        else:
            name = random.choices(_FISH_NAMES, weights=_FISH_WEIGHTS, k=1)[0]
            idx = _FISH_NAMES.index(name)
            coins = _FISH_COINS[idx] + random.randint(-5, 10)
            coins = max(1, coins)
            p["coins"] = p.get("coins", 0) + coins
            _save(d)
            await v2.send(ctx, v2.success(
                f"{settings.emoji.fish}  Catch!",
                f"You caught **{name}** and sold it for **{coins}** coins.\n"
                f"Balance: **{p['coins']:,}** coins.",
            ))

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

        # Roll loot
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
            f"You found something inside!",
            fields=[
                ("Item", item["name"]),
                ("Rarity", rarity_label),
                ("Sell Value", f"{item['sell']:,} coins" if item["sell"] > 0 else "Worthless junk"),
                ("Description", item["desc"]),
            ],
            footer=f"Sell it with !sell {loot_id} · {settings.bot_name} · built by {settings.creator}",
        ))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fishing(bot))
