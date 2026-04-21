"""Conversation cog — wake word, attachment, AI replies, learning."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Dict, Optional, Tuple

import discord
from discord.ext import commands

from .. import ai, embeds
from ..config import settings
from .fun import fetch_gif, GIF_CATEGORIES

log = logging.getLogger("york.conversation")


def _matches_any(text: str, phrases: tuple[str, ...]) -> bool:
    low = text.lower().strip()
    return any(low == p or low.startswith(p + " ") or low.startswith(p) and len(low) <= len(p) + 2 or p in low for p in phrases)


_NAME_REF = re.compile(r"\byork\b", re.IGNORECASE)


def _is_wake(text: str) -> Optional[str]:
    """Return the payload if the message starts with a wake phrase ('hey york' etc)."""
    low = text.lower().strip()
    for p in settings.wake_phrases:
        if low.startswith(p):
            stripped = text[len(p):].lstrip(" ,.!?:-")
            return stripped or "(no message)"
    return None


def _has_name(text: str) -> bool:
    """Does this message contain a bare reference to 'york'?"""
    return _NAME_REF.search(text) is not None


_GIF_TOKEN = re.compile(r"\[gif:([a-zA-Z]+)\]")


async def _extract_gifs(text: str) -> Tuple[str, list[str]]:
    """Pull `[gif:category]` tokens out of text and resolve them to URLs.

    Returns (cleaned_text, gif_urls). At most two GIFs per reply.
    """
    tokens = _GIF_TOKEN.findall(text)
    urls: list[str] = []
    for t in tokens[:2]:
        if t.lower() in GIF_CATEGORIES or t.lower() == "pet":
            u = await fetch_gif(t)
            if u:
                urls.append(u)
    cleaned = _GIF_TOKEN.sub("", text).strip()
    return cleaned, urls


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
        # Per-channel last-message timestamp — used to decide when the
        # channel has gone "quiet" enough for York to pipe up.
        self._last_activity: Dict[int, float] = {}
        # (channel_id, user_id) -> pending reply task. If a new reference
        # arrives from the same user, we cancel the old pending task and
        # schedule a fresh one so York replies to the latest thought.
        self._pending: Dict[Tuple[int, int], asyncio.Task] = {}

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

        # Mark channel activity for queued-reply pacing.
        self._last_activity[cid] = time.time()

        # PASSIVE LEARNING — York observes everyone's speech style on every
        # message in the server (whether he's being talked to or not) so his
        # replies can mirror how each person actually writes.
        for note in ai.infer_style_notes(text):
            mem.add_style_note(uid, note)

        wake_payload = _is_wake(text)
        is_mention = self.bot.user in (message.mentions or [])
        is_direct = wake_payload is not None or is_mention
        is_passing = not is_direct and _has_name(text)

        if is_direct:
            if wake_payload is not None:
                prompt = wake_payload
            else:
                prompt = re.sub(rf"<@!?{self.bot.user.id}>", "", text).strip() or "(no message)"
            # A direct address jumps the queue — cancel any pending passing
            # reply for this user and answer now.
            self._cancel_pending(cid, uid)
            await self.respond_to(message.channel, message.author, prompt, reply_to=message)
            return

        if is_passing:
            # Queued: York heard his name but doesn't want to interrupt.
            # Replace any older queued reply from the same user and wait
            # for the channel to quiet down before speaking.
            self._cancel_pending(cid, uid)
            task = asyncio.create_task(
                self._deferred_reply(message.channel, message.author, text, message)
            )
            self._pending[(cid, uid)] = task
            return

        # Otherwise: not addressed, not referenced → stay quiet.

    # --------- queued reply helpers ---------
    def _cancel_pending(self, cid: int, uid: int) -> None:
        task = self._pending.pop((cid, uid), None)
        if task and not task.done():
            task.cancel()

    async def _deferred_reply(
        self,
        channel: discord.abc.Messageable,
        user: discord.abc.User,
        prompt: str,
        reply_to: discord.Message,
    ) -> None:
        """Wait until the channel is quiet enough, then reply.

        Heuristic: don't speak until there have been at least ~4 seconds
        of no new messages in the channel, but give up and reply anyway
        after 20 seconds so he doesn't silently swallow the reference.
        """
        QUIET_REQUIRED = 4.0
        MAX_WAIT = 20.0
        started = time.time()
        try:
            while True:
                last = self._last_activity.get(channel.id, 0.0)
                since_quiet = time.time() - last
                if since_quiet >= QUIET_REQUIRED:
                    break
                if time.time() - started >= MAX_WAIT:
                    break
                await asyncio.sleep(min(1.0, QUIET_REQUIRED - since_quiet))
            await self.respond_to(channel, user, prompt, reply_to=reply_to)
        except asyncio.CancelledError:
            pass
        finally:
            self._pending.pop((channel.id, user.id), None)

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

        # Parse out any [gif:category] tokens York used in his reply and
        # resolve them to real GIF URLs. Discord auto-embeds image URLs
        # in plain messages, so we just send the URL on its own line.
        text_out, gif_urls = await _extract_gifs(answer)
        if not text_out and not gif_urls:
            text_out = answer  # fall back: shouldn't happen, but safe.

        # Plain chat-style reply — no embed, no buttons, just talks like a person.
        # Discord caps a single message at 2000 chars; chunk if needed.
        chunks = [text_out[i:i + 1900] for i in range(0, len(text_out), 1900)] or [""]
        for i, chunk in enumerate(chunks):
            if not chunk:
                continue
            if followup is not None and i == 0:
                await followup.send(content=chunk)
            elif reply_to is not None and i == 0:
                await reply_to.reply(content=chunk, mention_author=False)
            else:
                await channel.send(content=chunk)

        # Send any GIF URLs as follow-up messages (Discord auto-embeds them).
        for url in gif_urls:
            await channel.send(url)


class _null_ctx:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Conversation(bot))
