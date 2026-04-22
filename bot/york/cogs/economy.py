"""Economy & relationships — pay, shop, inventory, marriage, blackjack.

Builds on the same `bot/data/profiles.json` store the Fun cog uses, so
coins are shared everywhere (chat XP, daily, gambling, blackjack, shop
purchases, gifts to other players). New profile fields used here:

* `inventory`  -> list of item ids the user owns
* `married_to` -> user id of spouse (int) or None
* `married_at` -> unix timestamp of marriage
* `ring`       -> item id of the ring used for the current marriage
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import embeds
from ..config import settings
from .fun import _load, _save, _profile, _grant_xp


# ---------------------------------------------------------------------------
# Shop catalog
# ---------------------------------------------------------------------------
# Tiered rings + a few fun trinkets. Higher price = fancier description so
# proposing with a Celestial Halo actually feels like a flex.
SHOP_ITEMS: dict[str, dict] = {
    # rings (tier ascending)
    "ring_copper":   {"name": "Copper Band",        "price":     500, "type": "ring", "desc": "A simple copper band — humble but heartfelt."},
    "ring_silver":   {"name": "Silver Loop",        "price":   1_500, "type": "ring", "desc": "A polished silver loop with a soft shine."},
    "ring_gold":     {"name": "Gold Ring",          "price":   4_000, "type": "ring", "desc": "Classic gold. Timeless. Heavy in the hand."},
    "ring_rose":     {"name": "Rose-Gold Ring",     "price":   8_000, "type": "ring", "desc": "Warm pink-gold band. Elegant, vintage vibes."},
    "ring_sapphire": {"name": "Sapphire Ring",      "price":  16_000, "type": "ring", "desc": "Deep blue sapphire set in white gold."},
    "ring_emerald":  {"name": "Emerald Ring",       "price":  32_000, "type": "ring", "desc": "Vivid emerald flanked by tiny diamonds."},
    "ring_diamond":  {"name": "Diamond Ring",       "price":  75_000, "type": "ring", "desc": "Brilliant-cut diamond on a platinum band."},
    "ring_eternity": {"name": "Eternity Ring",      "price": 150_000, "type": "ring", "desc": "An unbroken circle of diamonds — forever."},
    "ring_celest":   {"name": "Celestial Halo",     "price": 500_000, "type": "ring", "desc": "A starlight-cut gem that glows faintly. Mythic."},
    # trinkets
    "rose":          {"name": "Single Rose",        "price":     100, "type": "gift",  "desc": "A fresh red rose. Simple gesture, big meaning."},
    "chocolates":    {"name": "Box of Chocolates",  "price":     250, "type": "gift",  "desc": "Twelve handmade chocolates in a glossy box."},
    "teddy":         {"name": "Plush Teddy Bear",   "price":     400, "type": "gift",  "desc": "A huggable bear wearing a tiny bow tie."},
    "crown":         {"name": "Tiny Crown",         "price":  10_000, "type": "trophy","desc": "A miniature crown. You're royalty now."},
    "yacht":         {"name": "Toy Yacht",          "price":  50_000, "type": "trophy","desc": "Pocket-sized yacht. You can dream."},
}


def _ring_ids() -> List[str]:
    return [k for k, v in SHOP_ITEMS.items() if v["type"] == "ring"]


def _item_pretty(item_id: str) -> str:
    item = SHOP_ITEMS.get(item_id)
    return item["name"] if item else item_id


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- pay / gift coins ----------------
    @commands.hybrid_command(name="pay", description="Send coins to another member.")
    @app_commands.describe(member="Who you're paying.", amount="How many coins (or 'all').")
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: str):
        if member.bot:
            await ctx.send(embed=embeds.warn("Nope", "You can't pay a bot."))
            return
        if member.id == ctx.author.id:
            await ctx.send(embed=embeds.warn("Nope", "You can't pay yourself."))
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
                await ctx.send(embed=embeds.danger("Bad amount", "Amount must be a number or `all`."))
                return

        if value <= 0:
            await ctx.send(embed=embeds.danger("Bad amount", "Amount must be positive."))
            return
        if value > bal:
            await ctx.send(embed=embeds.danger("Not enough coins", f"You only have **{bal}**."))
            return

        sender["coins"] = bal - value
        recv["coins"] = recv.get("coins", 0) + value
        _save(d)

        await ctx.send(embed=embeds.success(
            "Payment sent",
            f"{ctx.author.mention} sent **{value}** coins to {member.mention}.\n"
            f"Your balance: **{sender['coins']}** · their balance: **{recv['coins']}**.",
        ))

    # ---------------- shop ----------------
    @commands.hybrid_command(name="shop", description="Browse what you can buy with coins.")
    async def shop(self, ctx: commands.Context):
        rings = [(i, SHOP_ITEMS[i]) for i in _ring_ids()]
        gifts = [(i, v) for i, v in SHOP_ITEMS.items() if v["type"] in ("gift", "trophy")]

        e = embeds.info(
            f"{settings.emoji.spark}  York's Shop",
            "Buy with `!buy <id>`. Rings let you propose with `!marry @user`.",
        )
        e.add_field(
            name="Rings",
            value="\n".join(
                f"`{i}` · **{v['name']}** — {v['price']:,} coins\n*{v['desc']}*"
                for i, v in rings
            ),
            inline=False,
        )
        e.add_field(
            name="Gifts & Trinkets",
            value="\n".join(
                f"`{i}` · **{v['name']}** — {v['price']:,} coins\n*{v['desc']}*"
                for i, v in gifts
            ),
            inline=False,
        )
        await ctx.send(embed=e)

    @commands.hybrid_command(name="buy", description="Buy something from the shop by id.")
    @app_commands.describe(item_id="The shop item id (see /shop).")
    async def buy(self, ctx: commands.Context, item_id: str):
        item = SHOP_ITEMS.get(item_id.lower())
        if not item:
            await ctx.send(embed=embeds.danger("Unknown item", "Use `!shop` to see valid ids."))
            return

        d = _load(); p = _profile(d, ctx.author.id)
        bal = p.get("coins", 0)
        if bal < item["price"]:
            await ctx.send(embed=embeds.danger(
                "Not enough coins",
                f"**{item['name']}** costs **{item['price']:,}** coins. You have **{bal}**.",
            ))
            return

        p["coins"] = bal - item["price"]
        inv = p.setdefault("inventory", [])
        inv.append(item_id.lower())
        _save(d)

        await ctx.send(embed=embeds.success(
            f"Purchased {item['name']}",
            f"You spent **{item['price']:,}** coins. New balance: **{p['coins']}**.\n"
            f"Item added to your inventory.",
        ))

    # ---------------- inventory ----------------
    @commands.hybrid_command(name="inventory", description="Show your or someone's items.")
    @app_commands.describe(member="(Optional) whose inventory to view.")
    async def inventory(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        m = member or ctx.author
        d = _load(); p = _profile(d, m.id); _save(d)
        inv: list[str] = p.get("inventory", [])

        if not inv:
            await ctx.send(embed=embeds.info(f"{m.display_name}'s inventory", "Empty. Try `!shop` to buy something."))
            return

        # Group by item id with counts.
        counts: dict[str, int] = {}
        for x in inv:
            counts[x] = counts.get(x, 0) + 1

        lines = []
        for iid, n in counts.items():
            item = SHOP_ITEMS.get(iid)
            label = item["name"] if item else iid
            lines.append(f"• **{label}** ×{n}" if n > 1 else f"• **{label}**")

        e = embeds.info(f"{m.display_name}'s inventory", "\n".join(lines))
        e.set_thumbnail(url=m.display_avatar.url)
        await ctx.send(embed=e)

    # ---------------- marriage ----------------
    @commands.hybrid_command(name="marry", description="Propose to someone (requires a ring in your inventory).")
    @app_commands.describe(member="Who you're proposing to.")
    async def marry(self, ctx: commands.Context, member: discord.Member):
        if member.bot or member.id == ctx.author.id:
            await ctx.send(embed=embeds.warn("Nope", "Pick a real person, not yourself or a bot."))
            return

        d = _load()
        proposer = _profile(d, ctx.author.id)
        target = _profile(d, member.id)

        if proposer.get("married_to"):
            await ctx.send(embed=embeds.warn("You're already married", "Use `!divorce` first if you want to move on."))
            return
        if target.get("married_to"):
            await ctx.send(embed=embeds.warn("They're taken", f"{member.display_name} is already married to someone."))
            return

        # Find best ring in their inventory.
        inv: list[str] = proposer.get("inventory", [])
        owned_rings = [i for i in inv if SHOP_ITEMS.get(i, {}).get("type") == "ring"]
        if not owned_rings:
            await ctx.send(embed=embeds.danger(
                "You need a ring",
                "Buy one from `!shop` first — even a Copper Band counts.",
            ))
            return
        # Use the most expensive ring they own.
        ring_id = max(owned_rings, key=lambda i: SHOP_ITEMS[i]["price"])
        ring = SHOP_ITEMS[ring_id]

        # Ask the target to accept.
        view = _ProposalView(proposer_id=ctx.author.id, target_id=member.id)
        e = embeds.info(
            f"{settings.emoji.spark}  A proposal!",
            f"{ctx.author.mention} offers {member.mention} a **{ring['name']}** "
            f"and asks for their hand in marriage.\n\n"
            f"*{ring['desc']}*\n\n"
            f"{member.mention}, do you accept? (60s to decide)",
        )
        msg = await ctx.send(content=member.mention, embed=e, view=view)

        await view.wait()
        if view.result is None:
            await msg.edit(embed=embeds.warn("Proposal expired", f"{member.display_name} didn't answer in time."), view=None)
            return
        if view.result is False:
            await msg.edit(embed=embeds.danger("Declined", f"{member.display_name} said no. Awkward."), view=None)
            return

        # Accepted — re-load (other commands may have run during the wait).
        d2 = _load()
        p2 = _profile(d2, ctx.author.id)
        t2 = _profile(d2, member.id)
        if p2.get("married_to") or t2.get("married_to"):
            await msg.edit(embed=embeds.warn("Too late", "One of you got married in the meantime."), view=None)
            return

        # Consume the ring from inventory.
        inv2: list[str] = p2.get("inventory", [])
        if ring_id in inv2:
            inv2.remove(ring_id)

        now = time.time()
        p2["married_to"] = member.id
        p2["married_at"] = now
        p2["ring"] = ring_id
        t2["married_to"] = ctx.author.id
        t2["married_at"] = now
        t2["ring"] = ring_id
        _save(d2)

        await msg.edit(
            embed=embeds.success(
                "Married!",
                f"{ctx.author.mention} and {member.mention} are now married with a **{ring['name']}**. "
                f"Congratulations!",
            ),
            view=None,
        )

    @commands.hybrid_command(name="divorce", description="End your marriage.")
    async def divorce(self, ctx: commands.Context):
        d = _load(); p = _profile(d, ctx.author.id)
        spouse_id = p.get("married_to")
        if not spouse_id:
            await ctx.send(embed=embeds.warn("You're not married", "Nothing to end."))
            return
        s = _profile(d, int(spouse_id))
        for prof in (p, s):
            prof["married_to"] = None
            prof["ring"] = None
            prof["married_at"] = 0
        _save(d)

        spouse = ctx.guild.get_member(int(spouse_id)) if ctx.guild else None
        spouse_name = spouse.mention if spouse else f"<@{spouse_id}>"
        await ctx.send(embed=embeds.info("Divorced", f"{ctx.author.mention} and {spouse_name} are no longer married."))

    @commands.hybrid_command(name="marriage", description="See who you (or someone) are married to.")
    @app_commands.describe(member="(Optional) check someone else's marriage.")
    async def marriage(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        m = member or ctx.author
        d = _load(); p = _profile(d, m.id); _save(d)
        spouse_id = p.get("married_to")
        if not spouse_id:
            await ctx.send(embed=embeds.info(
                f"{m.display_name}'s marriage",
                "Single. Open to offers." if m.id == ctx.author.id else "Single.",
            ))
            return

        spouse = ctx.guild.get_member(int(spouse_id)) if ctx.guild else None
        spouse_name = spouse.display_name if spouse else f"User {spouse_id}"
        ring_id = p.get("ring")
        ring_name = _item_pretty(ring_id) if ring_id else "no ring on record"
        since = p.get("married_at", 0)
        days = int((time.time() - since) / 86400) if since else 0

        e = embeds.info(
            f"{m.display_name}'s marriage",
            f"Married to **{spouse_name}** with a **{ring_name}**.\n"
            f"Together for **{days}** day{'s' if days != 1 else ''}.",
        )
        if spouse:
            e.set_thumbnail(url=spouse.display_avatar.url)
        await ctx.send(embed=e)

    # ---------------- blackjack ----------------
    @commands.hybrid_command(name="blackjack", description="Play a hand of blackjack against York. Bet coins.")
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
                await ctx.send(embed=embeds.danger("Bad bet", "Bet must be a number or `all`."))
                return

        if amount <= 0:
            await ctx.send(embed=embeds.danger("Bad bet", "Bet must be positive."))
            return
        if amount > bal:
            await ctx.send(embed=embeds.danger("Not enough coins", f"You only have **{bal}**."))
            return

        # Lock the bet up-front. View settles winnings/refund at the end.
        p["coins"] = bal - amount
        _save(d)

        view = _BlackjackView(player=ctx.author, bet=amount)
        e = view.render(opening=True)
        msg = await ctx.send(embed=e, view=view)
        view.message = msg


# ===========================================================================
# Discord UI helpers
# ===========================================================================
class _ProposalView(discord.ui.View):
    """Yes/No buttons shown to the proposal target."""

    def __init__(self, proposer_id: int, target_id: int):
        super().__init__(timeout=60)
        self.proposer_id = proposer_id
        self.target_id = target_id
        self.result: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_id:
            await interaction.response.send_message(
                "This proposal isn't for you.", ephemeral=True,
            )
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
    """Best blackjack value of a hand (aces 1 or 11)."""
    total = 0
    aces = 0
    for card in hand:
        rank = card[:-1]
        if rank == "A":
            total += 11
            aces += 1
        elif rank in ("J", "Q", "K"):
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _is_blackjack(hand: list[str]) -> bool:
    return len(hand) == 2 and _hand_value(hand) == 21


def _hand_str(hand: list[str], hide_first: bool = False) -> str:
    if hide_first and hand:
        return "🂠 " + " ".join(f"`{c}`" for c in hand[1:])
    return " ".join(f"`{c}`" for c in hand)


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
        # Disable double-down once the player has hit at least once.
        self._can_double = True

    # ---- view utilities ----
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("This isn't your hand.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if not self.finished:
            # Treat as stand on timeout.
            await self._dealer_play_and_finish(reason="Timed out — auto-stand.")

    def render(self, opening: bool = False, footer: str | None = None) -> discord.Embed:
        pv = _hand_value(self.player_hand)
        if self.finished:
            dv = _hand_value(self.dealer_hand)
            dealer_line = f"{_hand_str(self.dealer_hand)}  → **{dv}**"
        else:
            dealer_line = f"{_hand_str(self.dealer_hand, hide_first=True)}  → **?**"

        title = "Blackjack"
        if opening and _is_blackjack(self.player_hand):
            title = "Blackjack — natural 21!"

        e = embeds.info(
            f"{settings.emoji.spark}  {title}",
            f"**Bet:** {self.bet} coins\n\n"
            f"**{self.player.display_name}**\n{_hand_str(self.player_hand)}  → **{pv}**\n\n"
            f"**Dealer**\n{dealer_line}",
        )
        if footer:
            e.set_footer(text=f"{footer} · York · built by {settings.creator}")
        return e

    # ---- buttons ----
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="➕")
    async def hit_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        self._can_double = False
        self.player_hand.append(self.deck.pop())
        if _hand_value(self.player_hand) >= 21:
            await interaction.response.defer()
            await self._dealer_play_and_finish()
            return
        await interaction.response.edit_message(embed=self.render(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()
        await self._dealer_play_and_finish()

    @discord.ui.button(label="Double", style=discord.ButtonStyle.success, emoji="⏫")
    async def double_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not self._can_double:
            await interaction.response.send_message("You can only double on your opening hand.", ephemeral=True)
            return
        # Need enough coins to cover the doubled portion.
        d = _load(); p = _profile(d, self.player.id)
        if p.get("coins", 0) < self.bet:
            await interaction.response.send_message(
                f"Not enough coins to double — you need another **{self.bet}**.",
                ephemeral=True,
            )
            return
        p["coins"] -= self.bet
        _save(d)
        self.bet *= 2
        self.player_hand.append(self.deck.pop())
        await interaction.response.defer()
        await self._dealer_play_and_finish()

    # ---- resolution ----
    async def _dealer_play_and_finish(self, reason: str | None = None) -> None:
        if self.finished:
            return
        # Dealer reveals & plays — hits until 17+.
        while _hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
            await asyncio.sleep(0)  # yield in case Discord is slow

        pv = _hand_value(self.player_hand)
        dv = _hand_value(self.dealer_hand)
        player_bj = _is_blackjack(self.player_hand)
        dealer_bj = _is_blackjack(self.dealer_hand)

        # Determine outcome and payout. `bet` was already deducted at start.
        d = _load(); p = _profile(d, self.player.id)
        payout = 0  # coins to credit back to the player.
        result_line = ""

        if pv > 21:
            result_line = f"You bust at **{pv}**. Dealer wins. **−{self.bet}** coins."
        elif player_bj and not dealer_bj:
            # 3:2 on natural blackjack.
            payout = int(self.bet * 2.5)
            result_line = f"Natural blackjack! Pays 3:2. **+{payout - self.bet}** coins."
        elif dv > 21:
            payout = self.bet * 2
            result_line = f"Dealer busts at **{dv}**. You win! **+{self.bet}** coins."
        elif pv > dv:
            payout = self.bet * 2
            result_line = f"**{pv}** beats **{dv}**. You win! **+{self.bet}** coins."
        elif pv < dv:
            result_line = f"**{dv}** beats **{pv}**. Dealer wins. **−{self.bet}** coins."
        else:
            payout = self.bet  # push — refund.
            result_line = f"Push at **{pv}**. Bet returned."

        if payout:
            p["coins"] = p.get("coins", 0) + payout
        # XP win bonus.
        _grant_xp(p, 6 if payout > self.bet else 2)
        _save(d)

        self.finished = True
        for child in self.children:
            child.disabled = True

        footer = reason or f"Balance: {p['coins']} coins"
        e = self.render(footer=f"{result_line}  ·  {footer}")
        if self.message:
            try:
                await self.message.edit(embed=e, view=self)
            except discord.HTTPException:
                pass
        self.stop()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
