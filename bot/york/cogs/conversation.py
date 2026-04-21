"""Conversation cog — wake word, attachment, AI replies, learning."""
from __future__ import annotations

import logging
import re
from typing import Optional

import discord
from discord.ext import commands

from .. import ai, embeds
from ..config import settings

log = logging.getLogger("york.conversation")


def _matches_any(text: str, phrases: tuple[str, ...]) -> bool:
    low = text.lower().strip()
    return any(low == p or low.startswith(p + " ") or low.startswith(p) and len(low) <= len(p) + 2 or p in low for p in phrases)


def _is_wake(text: str) -> Optional[str]:
    low = text.lower().strip()
    for p in settings.wake_phrases:
        if low.startswith(p):
            stripped = text[len(p):].lstrip(" ,.!?:-")
            return stripped or "(no message)"
    return None


def _is_detach(text: str) -> bool:
    low = re.sub(r"[^\w\s]", "", text.lower()).strip()
    for phrase in settings.detach_phrases:
        if low == phrase or low.startswith(phrase + " ") or low.endswith(" " + phrase):
            return True
    return False


class ReplyView(discord.ui.View):
    """Quick-action buttons attached to York's replies."""

    def __init__(self, cog: "Conversation", user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="Detach", style=discord.ButtonStyle.secondary)
    async def detach_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the person I'm chatting with can detach me.", ephemeral=True)
            return
        self.cog.bot.memory.detach(interaction.channel_id)
        await interaction.response.send_message(
            embed=embeds.info("Detaching", "Standing down. Say **Hey York** anytime."),
            ephemeral=True,
        )

    @discord.ui.button(label="Suggest something", style=discord.ButtonStyle.primary)
    async def suggest_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        await self.cog.respond_to(
            interaction.channel,
            interaction.user,
            "Surprise me — proactively suggest something fun, useful, or interesting for me right now.",
            followup=interaction.followup,
        )


class Conversation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --------- core listener ---------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        # don't intercept commands
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        text = message.content or ""
        if not text:
            return

        mem = self.bot.memory

        # PASSIVE LEARNING — York observes everyone's speech style, even
        # when he's not being addressed. He never replies from this; he
        # just remembers how each person talks so future replies feel right.
        for note in ai.infer_style_notes(text):
            mem.add_style_note(message.author.id, note)

        owner_id = mem.attached_user_for(message.channel.id)

        # detach (only the attached user can detach York)
        if owner_id == message.author.id and _is_detach(text):
            mem.detach(message.channel.id)
            await message.reply(
                embed=embeds.info("Standing down", f"{settings.emoji.wave} Talk to you later. Say **Hey York** to bring me back."),
                mention_author=False,
            )
            return

        # If someone else owns the channel, ignore everyone else completely —
        # York only listens to the person who activated him until they detach.
        if owner_id is not None and owner_id != message.author.id:
            return

        wake_payload = _is_wake(text)
        is_mention = self.bot.user in (message.mentions or [])

        prompt: Optional[str] = None
        if wake_payload is not None:
            prompt = wake_payload
            mem.attach(message.channel.id, message.author.id)
        elif is_mention:
            cleaned = re.sub(rf"<@!?{self.bot.user.id}>", "", text).strip()
            prompt = cleaned or "(no message)"
            mem.attach(message.channel.id, message.author.id)
        elif owner_id == message.author.id:
            prompt = text
            mem.touch_attachment(message.channel.id)

        if prompt is None:
            return

        await self.respond_to(message.channel, message.author, prompt, reply_to=message)

    # --------- self-awareness commands ---------
    @commands.hybrid_command(name="style", description="Show what York has learned about how you talk.")
    async def style(self, ctx: commands.Context, member: discord.Member | None = None):
        m = member or ctx.author
        notes = self.bot.memory.style_notes_for(m.id)
        msgs = len(self.bot.memory.transcript_for(m.id))
        if not notes:
            await ctx.send(embed=embeds.info(
                f"What I know about {m.display_name}",
                "Not much yet — I learn passively while you talk in the server. "
                f"({msgs} messages remembered between us so far.)",
            ))
            return
        body = "\n".join(f"{settings.emoji.spark} {n}" for n in notes)
        await ctx.send(embed=embeds.info(
            f"What I've picked up about {m.display_name}",
            f"{body}\n\n*Based on {msgs} of our messages I remember.*",
        ))

    @commands.hybrid_command(name="forgetme", description="Make York forget everything he's learned about you.")
    async def forgetme(self, ctx: commands.Context):
        self.bot.memory.clear_user(ctx.author.id)
        await ctx.send(embed=embeds.success("Memory wiped", "I've cleared everything I knew about you."))

    # --------- shared responder ---------
    async def respond_to(
        self,
        channel: discord.abc.Messageable,
        user: discord.abc.User,
        prompt: str,
        reply_to: discord.Message | None = None,
        followup: discord.Webhook | None = None,
    ) -> None:
        mem = self.bot.memory
        mem.append_message(user.id, "user", prompt)
        guild_ctx = ""
        if isinstance(channel, (discord.TextChannel, discord.Thread)) and channel.guild:
            g = channel.guild
            guild_ctx = (
                f"You are inside the Discord server '{g.name}' "
                f"({g.member_count} members). Channel: #{getattr(channel, 'name', '?')}."
            )
        msgs = ai.build_messages(
            mem.transcript_for(user.id),
            mem.style_notes_for(user.id),
            getattr(user, "display_name", str(user)),
            extra_context=guild_ctx,
        )
        async with channel.typing() if hasattr(channel, "typing") else _null_ctx():
            answer = await ai.chat(msgs)
        mem.append_message(user.id, "assistant", answer)

        embed = embeds.info(f"{settings.emoji.brain}  York", answer)
        view = ReplyView(self, user.id)
        if followup is not None:
            await followup.send(embed=embed, view=view)
        elif reply_to is not None:
            await reply_to.reply(embed=embed, view=view, mention_author=False)
        else:
            await channel.send(embed=embed, view=view)


class _null_ctx:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Conversation(bot))
