"""Economy & relationships — pay, shop, buy, inventory, rob, marry, divorce, blackjack, sell."""
from __future__ import annotations

import asyncio
import random
import time
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import v2
from ..config import settings
from .fun import _load, _save, _profile, _grant_xp

# ---------------------------------------------------------------------------
# Shop catalog
# ---------------------------------------------------------------------------
SHOP_ITEMS: dict[str, dict] = {
    "ring_copper":   {"name": "Copper Band",        "price":     500, "type": "ring",   "desc": "A simple copper band — humble but heartfelt."},
    "ring_silver":   {"name": "Silver Loop",        "price":   1_500, "type": "ring",   "desc": "A polished silver loop with a soft shine."},
    "ring_gold":     {"name": "Gold Ring",          "price":   4_000, "type": "ring",   "desc": "Classic gold. Timeless. Heavy in the hand."},
    "ring_rose":     {"name": "Rose-Gold Ring",     "price":   8_000, "type": "ring",   "desc": "Warm pink-gold band. Elegant, vintage vibes."},
    "ring_sapphire": {"name": "Sapphire Ring",      "price":  16_000, "type": "ring",   "desc": "Deep blue sapphire set in white gold."},
    "ring_emerald":  {"name": "Emerald Ring",       "price":  32_000, "type": "ring",   "desc": "Vivid emerald flanked by tiny diamonds."},
    "ring_diamond":  {"name": "Diamond Ring",       "price":  75_000, "type": "ring",   "desc": "Brilliant-cut diamond on a platinum band."},
    "ring_eternity": {"name": "Eternity Ring",      "price": 150_000, "type": "ring",   "desc": "An unbroken circle of diamonds — forever."},
    "ring_celest":   {"name": "Celestial Halo",     "price": 500_000, "type": "ring",   "desc": "A starlight-cut gem that glows faintly. Mythic."},
    "rose":          {"name": "Single Rose",        "price":     100, "type": "gift",   "desc": "A fresh red rose. Simple gesture, big meaning."},
    "chocolates":    {"name": "Box of Chocolates",  "price":     250, "type": "gift",   "desc": "Twelve handmade chocolates in a glossy box."},
    "teddy":         {"name": "Plush Teddy Bear",   "price":     400, "type": "gift",   "desc": "A huggable bear wearing a tiny bow tie."},
    "crown":         {"name": "Tiny Crown",         "price":  10_000, "type": "trophy", "desc": "A miniature crown. You're royalty now."},
    "yacht":         {"name": "Toy Yacht",          "price":  50_000, "type": "trophy", "desc": "Pocket-sized yacht. You can dream."},
}

# ---------------------------------------------------------------------------
# Sellable items (from fishing / crates)
# Sell price is what the player receives when they run !sell
# ---------------------------------------------------------------------------
SELLABLE_ITEMS: dict[str, dict] = {
    "old_boot":      {"name": "Old Boot",        "sell": 0,     "rarity": "common",    "desc": "Just a waterlogged boot. Worthless."},
    "seaweed":       {"name": "Pile of Seaweed", "sell": 5,     "rarity": "common",    "desc": "Slippery and pungent."},
    "pebble":        {"name": "Smooth Pebble",   "sell": 10,    "rarity": "common",    "desc": "A nicely rounded pebble."},
    "sea_glass":     {"name": "Sea Glass",       "sell": 40,    "rarity": "uncommon",  "desc": "Frosted glass polished by the sea."},
    "coral_piece":   {"name": "Coral Piece",     "sell": 80,    "rarity": "uncommon",  "desc": "A fragment of branching coral."},
    "barnacle_ring": {"name": "Barnacle Ring",   "sell": 90,    "rarity": "uncommon",  "desc": "A ring encrusted with barnacles."},
    "drift_bottle":  {"name": "Drift Bottle",    "sell": 150,   "rarity": "rare",      "desc": "A sealed bottle that washed ashore."},
    "fish_trophy":   {"name": "Fish Trophy",     "sell": 200,   "rarity": "rare",      "desc": "A small trophy shaped like a fish."},
    "pearl":         {"name": "Pearl",           "sell": 300,   "rarity": "rare",      "desc": "A lustrous pearl from a lucky oyster."},
    "ancient_coin":  {"name": "Ancient Coin",    "sell": 500,   "rarity": "epic",      "desc": "A coin worn smooth by centuries underwater."},
    "torn_map":      {"name": "Torn Map",        "sell": 250,   "rarity": "epic",      "desc": "Half a treasure map. Still counts."},
    "golden_fish":   {"name": "Golden Fish",     "sell": 1_000, "rarity": "legendary", "desc": "A fish that gleams like solid gold."},
}

_RARITY_WEIGHTS = {
    "common": 50, "uncommon": 30, "rare": 15, "epic": 4, "legendary": 1,
}

# Crate loot pool with weighted chances of each item or empty.
_CRATE_POOL: list[tuple[str | None, int]] = (
    [(None, 20)]  # 20% chance of nothing
    + [(iid, _RARITY_WEIGHTS[v["rarity"]]) for iid, v in SELLABLE_ITEMS.items()]
)

_CRATE_KEYS = [x[0] for x in _CRATE_POOL]
_CRATE_WEIGHTS = [x[1] for x in _CRATE_POOL]


def _ring_ids() -> List[str]:
    return [k for k, v in SHOP_ITEMS.items() if v["type"] == "ring"]


def _item_pretty(item_id: str) -> str:
    item = SHOP_ITEMS.get(item_id) or SELLABLE_ITEMS.get(item_id)
    return item["name"] if item else item_id


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- pay ----------------
    @commands.hybrid_command(name="pay", description="Send coins to another member.")
    @app_commands.describe(member="Who you're paying.", amount="How many coins (or 'all').")
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: str):
        if member.bot:
            await v2.send(ctx, v2.warn("Not Allowed", "You cannot pay a bot."))
            return
        if member.id == ctx.author.id:
            await v2.send(ctx, v2.warn("Not Allowed", "You cannot pay yourself."))
            return

        d = _load()
        sender = _profile(d, ctx.author.id)
        recv = _profile(d, member.id)
        bal = sender.get("coins", 0)

        amt_l = amount.strip().lower()
        if amt_l in ("all", "max"):
            value = bal
        else:
            try:
                value = int(amt_l)
            except ValueError:
                await v2.send(ctx, v2.danger("Bad Amount", "Amount must be a number or `all`."))
                return

        if value <= 0:
            await v2.send(ctx, v2.danger("Bad Amount", "Amount must be positive."))
            return
        if value > bal:
            await v2.send(ctx, v2.danger("Not Enough Coins", f"You only have **{bal:,}** coins."))
            return

        sender["coins"] = bal - value
        recv["coins"] = recv.get("coins", 0) + value
        _save(d)

        await v2.send(ctx, v2.success(
            "Payment Sent",
            f"{ctx.author.mention} sent **{value:,}** coins to {member.mention}.",
            fields=[
                ("Your Balance", f"{sender['coins']:,} coins"),
                ("Their Balance", f"{recv['coins']:,} coins"),
            ],
        ))

    # ---------------- rob ----------------
    @commands.hybrid_command(name="rob", description="Attempt to rob another member.")
    @app_commands.describe(member="Who you're trying to rob.")
    async def rob(self, ctx: commands.Context, member: discord.Member):
        if member.bot or member.id == ctx.author.id:
            await v2.send(ctx, v2.warn("Not Allowed", "Pick a real person to rob, not yourself or a bot."))
            return

        d = _load()
        robber = _profile(d, ctx.author.id)
        target = _profile(d, member.id)
        now = time.time()

        # Check caught cooldown (5 minutes)
        caught_until = robber.get("rob_caught_until", 0)
        if now < caught_until:
            remaining = int(caught_until - now)
            await v2.send(ctx, v2.danger(
                "Laying Low",
                f"You were caught recently and need to keep a low profile.\n"
                f"You can attempt another robbery in **{remaining // 60}m {remaining % 60}s**.",
            ))
            return

        target_coins = target.get("coins", 0)
        if target_coins < 100:
            await v2.send(ctx, v2.warn(
                "Not Worth It",
                f"{member.display_name} doesn't have enough coins to be worth robbing (minimum 100).",
            ))
            return

        # 35% success rate
        if random.random() < 0.35:
            # Success — steal 10–25% of their coins
            stolen = max(10, int(target_coins * random.uniform(0.10, 0.25)))
            stolen = min(stolen, target_coins)
            robber["coins"] = robber.get("coins", 0) + stolen
            target["coins"] = target_coins - stolen
            _grant_xp(robber, 10)
            _save(d)
            await v2.send(ctx, v2.success(
                "Heist Successful",
                f"You slipped away with **{stolen:,}** coins from {member.mention}!\n"
                f"New balance: **{robber['coins']:,}** coins.",
                thumbnail_url=member.display_avatar.url,
            ))
        else:
            # Caught — lose 5–15% of robber's coins, 5-min cooldown
            robber_coins = robber.get("coins", 0)
            fine = max(10, int(robber_coins * random.uniform(0.05, 0.15)))
            fine = min(fine, robber_coins)
            robber["coins"] = robber_coins - fine
            robber["rob_caught_until"] = now + 5 * 60  # 5 minutes
            _save(d)
            await v2.send(ctx, v2.danger(
                "Caught Red-Handed",
                f"{member.display_name} caught you in the act!\n"
                f"You were fined **{fine:,}** coins and must wait **5 minutes** before trying again.\n"
                f"New balance: **{robber['coins']:,}** coins.",
                thumbnail_url=ctx.author.display_avatar.url,
            ))

    # ---------------- shop ----------------
    @commands.hybrid_command(name="shop", description="Browse what you can buy with coins.")
    async def shop(self, ctx: commands.Context):
        rings = [(i, SHOP_ITEMS[i]) for i in _ring_ids()]
        gifts = [(i, v) for i, v in SHOP_ITEMS.items() if v["type"] in ("gift", "trophy")]

        ring_lines = "\n".join(
            f"`{i}` · **{v['name']}** — {v['price']:,}c\n*{v['desc']}*"
            for i, v in rings
        )
        gift_lines = "\n".join(
            f"`{i}` · **{v['name']}** — {v['price']:,}c\n*{v['desc']}*"
            for i, v in gifts
        )

        container = v2.build(
            "info",
            f"{settings.emoji.spark}  York's Shop",
            "Use `!buy <id>` to purchase. Rings allow you to propose with `!marry`.",
            extra_sections=[
                (f"**Rings**\n{ring_lines}", None),
                (f"**Gifts & Trinkets**\n{gift_lines}", None),
            ],
            footer=f"{settings.bot_name} · built by {settings.creator}",
        )
        await v2.send(ctx, container)

    @commands.hybrid_command(name="buy", description="Buy something from the shop by id.")
    @app_commands.describe(item_id="The shop item id (see /shop).")
    async def buy(self, ctx: commands.Context, item_id: str):
        item = SHOP_ITEMS.get(item_id.lower())
        if not item:
            await v2.send(ctx, v2.danger("Unknown Item", "Use `!shop` to see valid item ids."))
            return

        d = _load(); p = _profile(d, ctx.author.id)
        bal = p.get("coins", 0)
        if bal < item["price"]:
            await v2.send(ctx, v2.danger(
                "Not Enough Coins",
                f"**{item['name']}** costs **{item['price']:,}** coins.\nYou have **{bal:,}** coins.",
            ))
            return

        p["coins"] = bal - item["price"]
        inv = p.setdefault("inventory", [])
        inv.append(item_id.lower())
        _save(d)

        await v2.send(ctx, v2.success(
            f"Purchased — {item['name']}",
            f"You spent **{item['price']:,}** coins.\nNew balance: **{p['coins']:,}** coins.",
        ))

    # ---------------- sell ----------------
    @commands.hybrid_command(name="sell", description="Sell an item from your inventory for coins.")
    @app_commands.describe(item_id="Item id to sell (e.g. pearl). Use 'all' to sell everything sellable.", quantity="How many to sell (default 1).")
    async def sell(self, ctx: commands.Context, item_id: str, quantity: int = 1):
        d = _load(); p = _profile(d, ctx.author.id)
        inv: list[str] = p.get("inventory", [])

        if item_id.lower() == "all":
            # Sell all sellable items
            sold_count = 0
            total_earned = 0
            new_inv = []
            for iid in inv:
                sellable = SELLABLE_ITEMS.get(iid)
                if sellable and sellable["sell"] > 0:
                    total_earned += sellable["sell"]
                    sold_count += 1
                else:
                    new_inv.append(iid)
            p["inventory"] = new_inv
            p["coins"] = p.get("coins", 0) + total_earned
            _save(d)
            if sold_count == 0:
                await v2.send(ctx, v2.warn("Nothing to Sell", "You have no sellable items in your inventory."))
            else:
                await v2.send(ctx, v2.success(
                    "Items Sold",
                    f"Sold **{sold_count}** item{'s' if sold_count != 1 else ''} for **{total_earned:,}** coins.\n"
                    f"New balance: **{p['coins']:,}** coins.",
                ))
            return

        iid = item_id.lower()
        sellable = SELLABLE_ITEMS.get(iid)
        if not sellable:
            await v2.send(ctx, v2.danger("Not Sellable", f"`{iid}` is not a sellable item. Check your `!inventory`."))
            return
        if sellable["sell"] == 0:
            await v2.send(ctx, v2.warn("Worth Nothing", f"**{sellable['name']}** has no sale value — it's just junk."))
            return

        quantity = max(1, quantity)
        available = inv.count(iid)
        if available < quantity:
            await v2.send(ctx, v2.danger(
                "Not Enough",
                f"You only have **{available}** × {sellable['name']} in your inventory.",
            ))
            return

        total = sellable["sell"] * quantity
        for _ in range(quantity):
            inv.remove(iid)
        p["coins"] = p.get("coins", 0) + total
        _save(d)

        await v2.send(ctx, v2.success(
            "Sold",
            f"Sold **{quantity}** × {sellable['name']} for **{total:,}** coins.\n"
            f"New balance: **{p['coins']:,}** coins.",
        ))

    # ---------------- inventory ----------------
    @commands.hybrid_command(name="inventory", description="Show your or someone's items.")
    @app_commands.describe(member="(Optional) whose inventory to view.")
    async def inventory(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        m = member or ctx.author
        d = _load(); p = _profile(d, m.id); _save(d)
        inv: list[str] = p.get("inventory", [])

        if not inv:
            await v2.send(ctx, v2.info(
                f"{m.display_name}'s Inventory",
                "Empty. Try `!shop` to buy something or `!fish` to find items.",
                thumbnail_url=m.display_avatar.url,
            ))
            return

        counts: dict[str, int] = {}
        for x in inv:
            counts[x] = counts.get(x, 0) + 1

        lines = []
        for iid, n in sorted(counts.items()):
            item = SHOP_ITEMS.get(iid) or SELLABLE_ITEMS.get(iid)
            if item:
                label = item["name"]
                sell_note = f" *(sell: {item['sell']}c)*" if iid in SELLABLE_ITEMS and item.get("sell", 0) > 0 else ""
            else:
                label = iid
                sell_note = ""
            qty = f" ×{n}" if n > 1 else ""
            lines.append(f"• **{label}**{qty}{sell_note}")

        container = v2.build(
            "info",
            f"{m.display_name}'s Inventory",
            f"{len(inv)} item{'s' if len(inv) != 1 else ''} total.",
            extra_sections=[("\n".join(lines), None)],
            thumbnail_url=m.display_avatar.url,
        )
        await v2.send(ctx, container)

    # ---------------- marriage ----------------
    @commands.hybrid_command(name="marry", description="Propose to someone (requires a ring).")
    @app_commands.describe(member="Who you're proposing to.")
    async def marry(self, ctx: commands.Context, member: discord.Member):
        if member.bot or member.id == ctx.author.id:
            await v2.send(ctx, v2.warn("Not Allowed", "Pick a real person — not yourself or a bot."))
            return

        d = _load()
        proposer = _profile(d, ctx.author.id)
        target = _profile(d, member.id)

        if proposer.get("married_to"):
            await v2.send(ctx, v2.warn("Already Married", "Use `!divorce` first if you want to move on."))
            return
        if target.get("married_to"):
            await v2.send(ctx, v2.warn("They're Taken", f"{member.display_name} is already married to someone."))
            return

        inv: list[str] = proposer.get("inventory", [])
        owned_rings = [i for i in inv if SHOP_ITEMS.get(i, {}).get("type") == "ring"]
        if not owned_rings:
            await v2.send(ctx, v2.danger("No Ring", "You need a ring from `!shop` to propose — even a Copper Band counts."))
            return

        ring_id = max(owned_rings, key=lambda i: SHOP_ITEMS[i]["price"])
        ring = SHOP_ITEMS[ring_id]

        view = _ProposalView(proposer_id=ctx.author.id, target_id=member.id)
        container = v2.build(
            "info",
            f"{settings.emoji.spark}  A Proposal!",
            f"{ctx.author.mention} offers {member.mention} a **{ring['name']}** and asks for their hand in marriage.\n\n"
            f"*{ring['desc']}*\n\n"
            f"{member.mention}, do you accept? *(60 seconds to decide)*",
            footer=f"{settings.bot_name} · built by {settings.creator}",
        )
        msg = await v2.send(ctx, container, view=view)

        await view.wait()
        if view.result is None:
            await v2.edit(msg, v2.warn("Proposal Expired", f"{member.display_name} did not answer in time."))
            return
        if view.result is False:
            await v2.edit(msg, v2.danger("Proposal Declined", f"{member.display_name} said no."))
            return

        d2 = _load()
        p2 = _profile(d2, ctx.author.id)
        t2 = _profile(d2, member.id)
        if p2.get("married_to") or t2.get("married_to"):
            await v2.edit(msg, v2.warn("Too Late", "One of you got married in the meantime."))
            return

        inv2: list[str] = p2.get("inventory", [])
        if ring_id in inv2:
            inv2.remove(ring_id)

        now = time.time()
        p2["married_to"] = member.id; p2["married_at"] = now; p2["ring"] = ring_id
        t2["married_to"] = ctx.author.id; t2["married_at"] = now; t2["ring"] = ring_id
        _save(d2)

        await v2.edit(msg, v2.success(
            "Married! 💍",
            f"{ctx.author.mention} and {member.mention} are now married with a **{ring['name']}**.\n"
            f"Congratulations to the happy couple!",
        ))

    @commands.hybrid_command(name="divorce", description="End your marriage.")
    async def divorce(self, ctx: commands.Context):
        d = _load(); p = _profile(d, ctx.author.id)
        spouse_id = p.get("married_to")
        if not spouse_id:
            await v2.send(ctx, v2.warn("Not Married", "You are not currently married."))
            return
        s = _profile(d, int(spouse_id))
        for prof in (p, s):
            prof["married_to"] = None; prof["ring"] = None; prof["married_at"] = 0
        _save(d)
        spouse = ctx.guild.get_member(int(spouse_id)) if ctx.guild else None
        spouse_name = spouse.mention if spouse else f"<@{spouse_id}>"
        await v2.send(ctx, v2.info("Divorced", f"{ctx.author.mention} and {spouse_name} are no longer married."))

    @commands.hybrid_command(name="marriage", description="See who you (or someone) are married to.")
    @app_commands.describe(member="(Optional) check someone else's marriage.")
    async def marriage(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        m = member or ctx.author
        d = _load(); p = _profile(d, m.id); _save(d)
        spouse_id = p.get("married_to")
        if not spouse_id:
            msg = "Single — open to offers." if m.id == ctx.author.id else "Single."
            await v2.send(ctx, v2.info(f"{m.display_name}'s Marriage", msg, thumbnail_url=m.display_avatar.url))
            return

        spouse = ctx.guild.get_member(int(spouse_id)) if ctx.guild else None
        spouse_name = spouse.display_name if spouse else f"User {spouse_id}"
        ring_id = p.get("ring")
        ring_name = _item_pretty(ring_id) if ring_id else "no ring on record"
        since = p.get("married_at", 0)
        days = int((time.time() - since) / 86400) if since else 0

        await v2.send(ctx, v2.build(
            "info",
            f"💍  {m.display_name}'s Marriage",
            f"Married to **{spouse_name}**.",
            fields=[
                ("Ring", ring_name),
                ("Together For", f"{days} day{'s' if days != 1 else ''}"),
            ],
            thumbnail_url=(spouse.display_avatar.url if spouse else m.display_avatar.url),
        ))

    # ---------------- blackjack ----------------
    @commands.hybrid_command(name="blackjack", description="Play blackjack against York. Bet coins.")
    @app_commands.describe(bet="Coins to wager (or 'all').")
    async def blackjack(self, ctx: commands.Context, bet: str):
        d = _load(); p = _profile(d, ctx.author.id)
        bal = p.get("coins", 0)

        bet_l = bet.strip().lower()
        if bet_l in ("all", "max"):
            amount = bal
        else:
            try:
                amount = int(bet_l)
            except ValueError:
                await v2.send(ctx, v2.danger("Bad Bet", "Bet must be a number or `all`."))
                return

        if amount <= 0:
            await v2.send(ctx, v2.danger("Bad Bet", "Bet must be positive."))
            return
        if amount > bal:
            await v2.send(ctx, v2.danger("Not Enough Coins", f"You only have **{bal:,}** coins."))
            return

        p["coins"] = bal - amount; _save(d)

        view = _BlackjackView(player=ctx.author, bet=amount)
        container = view.render(opening=True)
        msg = await v2.send(ctx, container, view=view)
        view.message = msg

        # Auto-resolve natural blackjack immediately
        if _is_blackjack(view.player_hand):
            await view._dealer_play_and_finish()

    # ---------------- fight ----------------
    @commands.hybrid_command(name="fight", description="Challenge someone to a fight. Winner earns random coins.")
    @app_commands.describe(member="Who you want to fight.")
    async def fight(self, ctx: commands.Context, member: discord.Member):
        if member.bot or member.id == ctx.author.id:
            await v2.send(ctx, v2.warn("Not Allowed", "Pick a real person — not yourself or a bot."))
            return

        view = _FightView(challenger_id=ctx.author.id, target_id=member.id)
        msg = await v2.send(ctx, v2.build(
            "warn",
            "⚔️  Fight Challenge!",
            f"{ctx.author.mention} challenges {member.mention} to a fight!\n\n"
            f"Winner earns a random cash reward.\n\n"
            f"{member.mention}, do you accept? *(60 seconds)*",
            thumbnail_url=ctx.author.display_avatar.url,
            footer=f"{settings.bot_name} · built by {settings.creator}",
        ), view=view)

        await view.wait()

        if view.accepted is None:
            await v2.edit(msg, v2.warn("Challenge Expired", f"{member.display_name} didn't respond in time."))
            return
        if not view.accepted:
            await v2.edit(msg, v2.info("Backed Down", f"{member.display_name} refused the fight."))
            return

        challenger_wins = random.random() < 0.5
        winner, loser = (ctx.author, member) if challenger_wins else (member, ctx.author)

        prize = random.randint(50, 500)

        d = _load()
        w_prof = _profile(d, winner.id)
        w_prof["coins"] = w_prof.get("coins", 0) + prize
        _grant_xp(w_prof, 15)
        _save(d)

        flavours = [
            f"{winner.display_name} lands a decisive blow!",
            f"{loser.display_name} slips up — {winner.display_name} capitalises!",
            f"A close fight, but {winner.display_name} edges it at the last second!",
            f"{winner.display_name} barely survives but walks away victorious!",
            f"{winner.display_name} overpowers {loser.display_name} completely!",
        ]
        await v2.edit(msg, v2.success(
            f"⚔️  {winner.display_name} Wins!",
            f"{random.choice(flavours)}\n\n"
            f"💰 **{winner.display_name}** earns **{prize:,}** coins!\n"
            f"New balance: **{w_prof['coins']:,}** coins",
            thumbnail_url=winner.display_avatar.url,
        ))

    # ---------------- slots ----------------
    @commands.hybrid_command(name="slots", description="Spin the slot machine and bet coins.")
    @app_commands.describe(bet="Coins to bet (or 'all').")
    async def slots(self, ctx: commands.Context, bet: str):
        d = _load(); p = _profile(d, ctx.author.id)
        bal = p.get("coins", 0)

        bet_l = bet.strip().lower()
        if bet_l in ("all", "max"):
            amount = bal
        else:
            try:
                amount = int(bet_l)
            except ValueError:
                await v2.send(ctx, v2.danger("Bad Bet", "Bet must be a number or `all`."))
                return

        if amount <= 0:
            await v2.send(ctx, v2.danger("Bad Bet", "Bet must be positive."))
            return
        if amount > bal:
            await v2.send(ctx, v2.danger("Not Enough Coins", f"You only have **{bal:,}** coins."))
            return

        # Deduct bet up front
        p["coins"] = bal - amount
        _save(d)

        # Send spinning message, then animate for ~5 seconds
        msg = await v2.send(ctx, _slots_spin_embed(amount))
        for _ in range(5):
            await asyncio.sleep(0.9)
            await v2.edit(msg, _slots_spin_embed(amount))

        # Final spin — determine result
        reels = _spin()
        outcome, mult = _eval_spin(reels)
        winnings = int(amount * mult)
        net = winnings - amount

        d2 = _load(); p2 = _profile(d2, ctx.author.id)
        p2["coins"] = p2.get("coins", 0) + winnings
        _grant_xp(p2, 3 if net >= 0 else 1)
        _save(d2)

        view = _SlotsView(player=ctx.author, bet=amount)
        await v2.edit(msg, _slots_embed(ctx.author, reels, outcome, net, amount, p2["coins"]), view=view)

    # ---------------- race ----------------
    @commands.hybrid_command(name="race", description="Bet on a horse race. Pick your horse and cross your fingers.")
    @app_commands.describe(bet="Coins to wager (or 'all').")
    async def race(self, ctx: commands.Context, bet: str):
        d = _load(); p = _profile(d, ctx.author.id)
        bal = p.get("coins", 0)

        bet_l = bet.strip().lower()
        if bet_l in ("all", "max"):
            amount = bal
        else:
            try:
                amount = int(bet_l)
            except ValueError:
                await v2.send(ctx, v2.danger("Bad Bet", "Bet must be a number or `all`."))
                return

        if amount <= 0:
            await v2.send(ctx, v2.danger("Bad Bet", "Bet must be positive."))
            return
        if amount > bal:
            await v2.send(ctx, v2.danger("Not Enough Coins", f"You only have **{bal:,}** coins."))
            return

        stat_blocks = []
        for h in _HORSES:
            spd = "█" * h["speed"]   + "░" * (10 - h["speed"])
            sta = "█" * h["stamina"] + "░" * (10 - h["stamina"])
            lck = "█" * h["luck"]    + "░" * (10 - h["luck"])
            stat_blocks.append(
                f"{h['emoji']} **{h['name']}**\n"
                f"Speed    `{spd}`\n"
                f"Stamina  `{sta}`\n"
                f"Luck     `{lck}`"
            )

        view = _RaceView(player_id=ctx.author.id)
        msg = await v2.send(ctx, v2.build(
            "info",
            "🏇  Horse Racing — Pick Your Horse",
            f"**Bet:** {amount:,} coins · Win pays **2×** · High stats help but don't guarantee a win!\n\n"
            + "\n\n".join(stat_blocks),
            footer=f"{settings.bot_name} · built by {settings.creator}",
        ), view=view)

        await view.wait()

        if view.chosen is None:
            await v2.edit(msg, v2.warn("Abandoned", "You didn't pick a horse in time. No coins deducted."))
            return

        d = _load(); p = _profile(d, ctx.author.id)
        if p.get("coins", 0) < amount:
            await v2.edit(msg, v2.danger("Not Enough Coins", "Your balance changed — race cancelled."))
            return
        p["coins"] = p.get("coins", 0) - amount
        _save(d)

        chosen = _HORSES[view.chosen]

        # Determine winner and pre-build animation frames
        winner_idx = _race_result()
        winner_horse = _HORSES[winner_idx]
        frames = _race_frames(winner_idx)

        # Animate the race
        for tick, positions in enumerate(frames):
            progress = _race_progress_text(positions)
            header = f"You backed {chosen['emoji']} **{chosen['name']}** — race is on!\n\n"
            await v2.edit(msg, v2.build(
                "info", "🏇  Racing…",
                header + progress,
                footer=f"{settings.bot_name} · built by {settings.creator}",
            ))
            await asyncio.sleep(0.9)

        others = [i for i in range(len(_HORSES)) if i != winner_idx]
        random.shuffle(others)
        order = [winner_idx] + others
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        finish_line = "\n".join(
            f"{medals[rank]} {_HORSES[pos]['emoji']} **{_HORSES[pos]['name']}**"
            for rank, pos in enumerate(order)
        )

        d = _load(); p = _profile(d, ctx.author.id)
        if winner_idx == view.chosen:
            prize = amount * 2
            p["coins"] = p.get("coins", 0) + prize
            _grant_xp(p, 20)
            _save(d)
            await v2.edit(msg, v2.success(
                f"🏇  {winner_horse['name']} Wins!",
                f"Your horse came first! 🎉\n\n{finish_line}\n\n"
                f"💰 **+{amount:,} coins** · Balance: **{p['coins']:,}**",
            ))
        else:
            _grant_xp(p, 2)
            _save(d)
            await v2.edit(msg, v2.danger(
                f"🏇  {winner_horse['name']} Wins!",
                f"Your horse {chosen['emoji']} **{chosen['name']}** didn't win.\n\n"
                f"{finish_line}\n\n"
                f"💸 **−{amount:,} coins** · Balance: **{p['coins']:,}**",
            ))


# ===========================================================================
# UI helpers
# ===========================================================================
class _ProposalView(discord.ui.View):
    def __init__(self, proposer_id: int, target_id: int):
        super().__init__(timeout=60)
        self.proposer_id = proposer_id
        self.target_id = target_id
        self.result: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_id:
            await interaction.response.send_message("This proposal is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, I do!", style=discord.ButtonStyle.success, emoji="💍")
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.result = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="No thanks", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.result = False
        await interaction.response.defer()
        self.stop()


# ---------- Blackjack engine ----------
_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
_SUITS = ["♠", "♥", "♦", "♣"]


def _new_deck() -> list[str]:
    deck = [f"{r}{s}" for r in _RANKS for s in _SUITS]
    random.shuffle(deck)
    return deck


def _hand_value(hand: list[str]) -> int:
    total = 0; aces = 0
    for card in hand:
        rank = card[:-1]
        if rank == "A":
            total += 11; aces += 1
        elif rank in ("J", "Q", "K"):
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10; aces -= 1
    return total


def _is_blackjack(hand: list[str]) -> bool:
    return len(hand) == 2 and _hand_value(hand) == 21


def _hand_str(hand: list[str], hide_first: bool = False) -> str:
    if hide_first and hand:
        return "🂠 " + " ".join(f"`{c}`" for c in hand[1:])
    return " ".join(f"`{c}`" for c in hand)


# ---- Slots engine ----
_SLOT_SYMS = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣"]
_SLOT_W    = [30, 25, 20, 15, 5, 3, 2]
_SLOT_PAY: dict = {
    ("7️⃣", 3): 20, ("💎", 3): 10, ("🔔", 3): 5,
    ("🍇", 3): 4,  ("🍊", 3): 3,  ("🍋", 3): 2.5, ("🍒", 3): 2,
}


def _spin() -> list[str]:
    return random.choices(_SLOT_SYMS, weights=_SLOT_W, k=3)


def _eval_spin(reels: list[str]) -> tuple[str, float]:
    r1, r2, r3 = reels
    if r1 == r2 == r3:
        return f"Three {r1}!", _SLOT_PAY.get((r1, 3), 2.0)
    if r1 == r2 or r2 == r3 or r1 == r3:
        return "Two of a kind", 0.5
    return "No match", 0.0


def _slots_spin_embed(bet: int) -> discord.Embed:
    r = random.choices(_SLOT_SYMS, weights=_SLOT_W, k=3)
    return v2.build(
        "info",
        f"{settings.emoji.spark}  Slot Machine",
        f"┃ {'  '.join(r)} ┃\n\n🎰 *Spinning…*",
        fields=[("Bet", f"{bet:,}c")],
        footer=f"{settings.bot_name} · built by {settings.creator}",
    )


def _slots_embed(
    player: discord.abc.User,
    reels: list[str],
    outcome: str,
    net: int,
    bet: int,
    bal: int,
) -> discord.Embed:
    reel_display = "  ".join(reels)
    if net > 0:
        style, result = "success", f"💰 **+{net:,} coins** — {outcome}"
    elif net == 0:
        style, result = "info", f"↔️ Broke even — {outcome}"
    else:
        style, result = "danger", f"💸 **−{abs(net):,} coins** — {outcome}"
    return v2.build(
        style,
        f"{settings.emoji.spark}  Slot Machine",
        f"┃ {reel_display} ┃\n\n{result}",
        fields=[("Bet", f"{bet:,}c"), ("Balance", f"{bal:,}c")],
        extra_sections=[(
            "**Payouts:**\n"
            "7️⃣7️⃣7️⃣ → **20×** · 💎💎💎 → **10×** · 🔔🔔🔔 → **5×**\n"
            "🍇🍇🍇 → **4×** · 🍊🍊🍊 → **3×** · 🍋🍋🍋 → **2.5×** · 🍒🍒🍒 → **2×**\n"
            "Two matching → **0.5×** (half back)", None,
        )],
        footer=f"{settings.bot_name} · built by {settings.creator}",
    )


# ---- Horse racing engine ----
_HORSES = [
    {"name": "Thunder Bolt",  "emoji": "🟡", "speed": 9, "stamina": 6, "luck": 5},
    {"name": "Shadow Dancer", "emoji": "⚫", "speed": 7, "stamina": 8, "luck": 7},
    {"name": "Golden Arrow",  "emoji": "🟠", "speed": 8, "stamina": 7, "luck": 6},
    {"name": "Silver Storm",  "emoji": "⚪", "speed": 6, "stamina": 9, "luck": 8},
    {"name": "Lucky Charm",   "emoji": "🟢", "speed": 5, "stamina": 7, "luck": 10},
]


def _race_result() -> int:
    weights = []
    for h in _HORSES:
        base = h["speed"] * 0.4 + h["stamina"] * 0.3 + h["luck"] * 0.3
        weights.append(max(0.5, base + random.gauss(0, 1.5)))
    return random.choices(range(len(_HORSES)), weights=weights, k=1)[0]


def _race_frames(winner_idx: int, ticks: int = 5, track: int = 12) -> list[list[int]]:
    """Return `ticks` animation frames of horse positions (0–track).
    The winner is guaranteed to reach `track` on the final frame."""
    speeds = [
        (h["speed"] * 0.4 + h["stamina"] * 0.3 + h["luck"] * 0.3) / 10
        for h in _HORSES
    ]
    total = sum(speeds)
    positions = [0.0] * len(_HORSES)
    frames = []
    for tick in range(ticks):
        for i in range(len(_HORSES)):
            step = (speeds[i] / total) * track * (1.3 / ticks) + random.uniform(-0.4, 0.6)
            positions[i] = min(track, max(0.0, positions[i] + step))
        if tick == ticks - 1:
            positions[winner_idx] = float(track)
            for i in range(len(_HORSES)):
                if i != winner_idx:
                    positions[i] = min(float(track) - 1.0, positions[i])
        frames.append([min(track, max(0, int(p))) for p in positions])
    return frames


def _race_progress_text(positions: list[int], track: int = 12) -> str:
    lines = []
    for i, h in enumerate(_HORSES):
        pos = min(track, positions[i])
        at_end = pos >= track
        marker = "🏆" if at_end else "🏇"
        bar = "▬" * pos + marker + "·" * max(0, track - pos - (0 if at_end else 1))
        flag = " 🏁" if at_end else ""
        lines.append(f"{h['emoji']} **{h['name']:<14}** `{bar}`{flag}")
    return "\n".join(lines)


class _BlackjackView(discord.ui.View):
    def __init__(self, player: discord.abc.User, bet: int):
        super().__init__(timeout=120)
        self.player = player
        self.bet = bet
        self.deck = _new_deck()
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        self.finished = False
        self.message: Optional[discord.Message] = None
        self._can_double = True
        self.outcome: Optional[str] = None
        self.delta: int = 0
        self.balance_after: int = 0

        self._btn_hit = discord.ui.Button(label="Hit", style=discord.ButtonStyle.primary, emoji="➕")
        self._btn_stand = discord.ui.Button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋")
        self._btn_double = discord.ui.Button(label="Double Down", style=discord.ButtonStyle.success, emoji="⏫")
        self._btn_hit.callback = self._on_hit
        self._btn_stand.callback = self._on_stand
        self._btn_double.callback = self._on_double
        self.add_item(self._btn_hit)
        self.add_item(self._btn_stand)
        self.add_item(self._btn_double)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("This is not your hand.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if not self.finished:
            await self._dealer_play_and_finish()

    def _disable_all(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    def render(self, opening: bool = False) -> discord.Embed:
        pv = _hand_value(self.player_hand)
        if self.finished:
            dv = _hand_value(self.dealer_hand)
            dealer_line = f"{_hand_str(self.dealer_hand)}  → **{dv}**"
        else:
            dealer_line = f"{_hand_str(self.dealer_hand, hide_first=True)}  → **?**"

        if not self.finished:
            style = "info"
            title = "Blackjack — Natural 21!" if opening and _is_blackjack(self.player_hand) else "Blackjack"
            banner = ""
        else:
            banner_map = {
                "blackjack": ("success", "YOU WIN — Blackjack! 🎉", f"💰 **+{self.delta:,} coins** (3:2 payout)"),
                "win":       ("success", "YOU WIN! 🎉",             f"💰 **+{self.delta:,} coins**"),
                "push":      ("info",    "PUSH — Tie",              f"↔️ Bet of **{self.bet:,}** returned."),
                "bust":      ("danger",  "YOU LOSE — Bust! 💸",     f"**−{abs(self.delta):,} coins**"),
                "lose":      ("danger",  "YOU LOSE 💸",             f"**−{abs(self.delta):,} coins**"),
            }
            style, title, banner = banner_map.get(self.outcome or "lose", banner_map["lose"])

        body = (f"**{banner}**\n\n" if banner else "") + f"Bet: **{self.bet:,}** coins"
        footer = (
            f"Balance: {self.balance_after:,} coins · {settings.bot_name} · built by {settings.creator}"
            if self.finished else
            f"{settings.bot_name} · built by {settings.creator}"
        )
        return v2.build(
            style,
            f"{settings.emoji.spark}  {title}",
            body,
            extra_sections=[
                (f"**{self.player.display_name}**\n{_hand_str(self.player_hand)}  → **{pv}**\n\n"
                 f"**Dealer**\n{dealer_line}", None),
            ],
            footer=footer,
        )

    async def _on_hit(self, interaction: discord.Interaction) -> None:
        self._can_double = False
        self.player_hand.append(self.deck.pop())
        if _hand_value(self.player_hand) >= 21:
            await interaction.response.defer()
            await self._dealer_play_and_finish()
            return
        await interaction.response.edit_message(embed=self.render(), view=self)

    async def _on_stand(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._dealer_play_and_finish()

    async def _on_double(self, interaction: discord.Interaction) -> None:
        if not self._can_double:
            await interaction.response.send_message("You can only double on your opening hand.", ephemeral=True)
            return
        d = _load(); p = _profile(d, self.player.id)
        if p.get("coins", 0) < self.bet:
            await interaction.response.send_message(
                f"Not enough coins to double — you need another **{self.bet:,}**.", ephemeral=True,
            )
            return
        p["coins"] -= self.bet; _save(d)
        self.bet *= 2
        self.player_hand.append(self.deck.pop())
        await interaction.response.defer()
        await self._dealer_play_and_finish()

    async def _dealer_play_and_finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        self._disable_all()

        pv = _hand_value(self.player_hand)
        if pv > 21:
            self.outcome = "bust"
            self.delta = -self.bet
        else:
            while _hand_value(self.dealer_hand) < 17:
                self.dealer_hand.append(self.deck.pop())
            dv = _hand_value(self.dealer_hand)
            if _is_blackjack(self.player_hand) and not _is_blackjack(self.dealer_hand):
                self.outcome = "blackjack"
                self.delta = int(self.bet * 1.5)
            elif dv > 21 or pv > dv:
                self.outcome = "win"
                self.delta = self.bet
            elif pv == dv:
                self.outcome = "push"
                self.delta = 0
            else:
                self.outcome = "lose"
                self.delta = -self.bet

        d = _load(); p = _profile(d, self.player.id)
        p["coins"] = p.get("coins", 0) + self.bet + self.delta
        _grant_xp(p, 5 if self.delta >= 0 else 2)
        _save(d)
        self.balance_after = p["coins"]

        if self.message:
            await v2.edit(self.message, self.render(), view=self)
        self.stop()


# ---------- Fight view ----------
class _FightView(discord.ui.View):
    def __init__(self, challenger_id: int, target_id: int):
        super().__init__(timeout=60)
        self.challenger_id = challenger_id
        self.target_id = target_id
        self.accepted: Optional[bool] = None

        btn_accept = discord.ui.Button(label="Accept Fight", style=discord.ButtonStyle.danger, emoji="⚔️")
        btn_decline = discord.ui.Button(label="Back Down", style=discord.ButtonStyle.secondary, emoji="🏃")
        btn_accept.callback = self._on_accept
        btn_decline.callback = self._on_decline
        self.add_item(btn_accept)
        self.add_item(btn_decline)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_id:
            await interaction.response.send_message("This challenge isn't for you.", ephemeral=True)
            return False
        return True

    async def _on_accept(self, interaction: discord.Interaction) -> None:
        self.accepted = True
        await interaction.response.defer()
        self.stop()

    async def _on_decline(self, interaction: discord.Interaction) -> None:
        self.accepted = False
        await interaction.response.defer()
        self.stop()


# ---------- Slots view ----------
class _SlotsView(discord.ui.View):
    def __init__(self, player: discord.abc.User, bet: int):
        super().__init__(timeout=30)
        self.player = player
        self.bet = bet

        btn = discord.ui.Button(label="Spin Again", style=discord.ButtonStyle.primary, emoji="🎰")
        btn.callback = self._on_spin
        self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("These aren't your slots!", ephemeral=True)
            return False
        return True

    async def _on_spin(self, interaction: discord.Interaction) -> None:
        d = _load(); p = _profile(d, self.player.id)
        if p.get("coins", 0) < self.bet:
            await interaction.response.send_message(
                f"Not enough coins to spin again (need **{self.bet:,}**).", ephemeral=True
            )
            return
        reels = _spin()
        outcome, mult = _eval_spin(reels)
        winnings = int(self.bet * mult)
        net = winnings - self.bet
        p["coins"] = p.get("coins", 0) - self.bet + winnings
        _grant_xp(p, 3 if net >= 0 else 1)
        _save(d)
        await interaction.response.edit_message(
            embed=_slots_embed(self.player, reels, outcome, net, self.bet, p["coins"]),
            view=self,
        )


# ---------- Horse racing view ----------
class _HorseBtn(discord.ui.Button):
    def __init__(self, idx: int, horse: dict):
        super().__init__(label=horse["name"], style=discord.ButtonStyle.primary, emoji=horse["emoji"])
        self.idx = idx

    async def callback(self, interaction: discord.Interaction) -> None:
        view: _RaceView = self.view  # type: ignore
        view.chosen = self.idx
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.defer()
        view.stop()


class _RaceView(discord.ui.View):
    def __init__(self, player_id: int):
        super().__init__(timeout=60)
        self.player_id = player_id
        self.chosen: Optional[int] = None
        for i, h in enumerate(_HORSES):
            self.add_item(_HorseBtn(i, h))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This race isn't yours to bet on.", ephemeral=True)
            return False
        return True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
