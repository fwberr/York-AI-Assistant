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
        self.cog.bot.memory.detach(interaction.channel_id, self.user_id)
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
        cid = message.channel.id
        uid = message.author.id

        # PASSIVE LEARNING — York observes everyone's speech style on every
        # message in the server (whether he's being talked to or not) so his
        # replies can mirror how each person actually writes.
        for note in ai.infer_style_notes(text):
            mem.add_style_note(uid, note)

        attached = mem.is_attached(cid, uid)

        # Detach only ends THIS user's session — other people's sessions
        # in the same channel keep going.
        if attached and _is_detach(text):
            mem.detach(cid, uid)
            await message.reply(
                embed=embeds.info("Standing down", f"{settings.emoji.wave} Talk to you later. Say **Hey York** to bring me back."),
                mention_author=False,
            )
            return

        wake_payload = _is_wake(text)
        is_mention = self.bot.user in (message.mentions or [])

        prompt: Optional[str] = None
        if wake_payload is not None:
            prompt = wake_payload
            mem.attach(cid, uid)
        elif is_mention:
            cleaned = re.sub(rf"<@!?{self.bot.user.id}>", "", text).strip()
            prompt = cleaned or "(no message)"
            mem.attach(cid, uid)
        elif attached:
            prompt = text
            mem.touch_attachment(cid, uid)

        if prompt is None:
            return

        await self.respond_to(message.channel, message.author, prompt, reply_to=message)

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
