"""Conversation cog — wake word, attachment, AI replies."""
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
from .fun import fetch_gif, fetch_gif_search, fetch_image, GIF_CATEGORIES

log = logging.getLogger("york.conversation")

# Regex to detect @everyone and @here that the AI might slip in.
_MASS_PING = re.compile(r"@(?:everyone|here)", re.IGNORECASE)


def _matches_any(text: str, phrases: tuple[str, ...]) -> bool:
    low = text.lower().strip()
    return any(low == p or low.startswith(p + " ") or p in low for p in phrases)


_NAME_REF = re.compile(r"\byork\b", re.IGNORECASE)


def _is_wake(text: str) -> Optional[str]:
    low = text.lower().strip()
    for p in settings.wake_phrases:
        if low.startswith(p):
            stripped = text[len(p):].lstrip(" ,.!?:-")
            return stripped or "(no message)"
    return None


def _has_name(text: str) -> bool:
    return _NAME_REF.search(text) is not None


_GIF_TOKEN = re.compile(r"\[gif:([^\]\n]{1,60})\]")
_IMG_TOKEN = re.compile(r"\[img:([^\]\n]{1,80})\]")


def _resolve_gif_action(token: str) -> str | None:
    """Return a valid GIF category only for single-word reaction tokens.

    Multi-word queries (e.g. 'astolfo blush', 'cat sleeping') are sent to
    GIF search so the full intent is preserved — extracting just 'blush'
    from 'astolfo blush' would return a generic GIF, not an Astolfo one.
    """
    token = token.strip().lower()
    alias = {"pet": "pat"}
    words = token.split()
    # Only resolve to a reaction category when the token is a single word
    if len(words) == 1:
        c = alias.get(token, token)
        return c if c in GIF_CATEGORIES else None
    return None


async def _extract_media(text: str) -> Tuple[str, list[str]]:
    urls: list[str] = []
    for t in _GIF_TOKEN.findall(text)[:2]:
        action = _resolve_gif_action(t)
        if action:
            # Known reaction category → nekos.best (anime style)
            u = await fetch_gif(action)
        else:
            # Anything else (character name, custom query) → Tenor search
            u = await fetch_gif_search(t.strip())
        if u:
            urls.append(u)
    for q in _IMG_TOKEN.findall(text)[:2]:
        u = await fetch_image(q)
        if u:
            urls.append(u)
    cleaned = _IMG_TOKEN.sub("", _GIF_TOKEN.sub("", text)).strip()
    return cleaned, urls[:3]


def _is_detach(text: str) -> bool:
    low = re.sub(r"[^\w\s]", "", text.lower()).strip()
    for phrase in settings.detach_phrases:
        if low == phrase or low.startswith(phrase + " ") or low.endswith(" " + phrase):
            return True
    return False


def _sanitize_ai_output(text: str) -> str:
    """Remove @everyone and @here from AI-generated output."""
    return _MASS_PING.sub(lambda m: m.group(0).replace("@", "@ "), text)


class ReplyView(discord.ui.View):
    def __init__(self, cog: "Conversation", user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="Detach", style=discord.ButtonStyle.secondary)
    async def detach_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person I am speaking with can detach me.", ephemeral=True,
            )
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
            "Suggest something useful, interesting, or helpful for me right now.",
            followup=interaction.followup,
        )


class Conversation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_activity: Dict[int, float] = {}
        self._pending: Dict[Tuple[int, int], asyncio.Task] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        text = message.content or ""
        if not text:
            return

        mem = self.bot.memory
        cid = message.channel.id
        uid = message.author.id

        self._last_activity[cid] = time.time()

        for note in ai.infer_style_notes(text):
            mem.add_style_note(uid, note)

        wake_payload = _is_wake(text)
        is_mention = self.bot.user in (message.mentions or [])
        is_direct = wake_payload is not None or is_mention
        is_passing = not is_direct and _has_name(text)

        if is_direct:
            prompt = wake_payload if wake_payload is not None else (
                re.sub(rf"<@!?{self.bot.user.id}>", "", text).strip() or "(no message)"
            )
            self._cancel_pending(cid, uid)
            await self.respond_to(message.channel, message.author, prompt, reply_to=message)
            return

        if is_passing:
            self._cancel_pending(cid, uid)
            task = asyncio.create_task(
                self._deferred_reply(message.channel, message.author, text, message)
            )
            self._pending[(cid, uid)] = task
            return

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

        # Strip any mass pings the AI might have produced.
        answer = _sanitize_ai_output(answer)
        mem.append_message(user.id, "assistant", answer)

        text_out, gif_urls = await _extract_media(answer)
        if not text_out and not gif_urls:
            # If the AI only sent media tokens and all fetches failed, don't
            # echo the raw token text back — just send nothing this turn.
            has_media_tokens = bool(_GIF_TOKEN.search(answer) or _IMG_TOKEN.search(answer))
            if not has_media_tokens:
                text_out = answer

        chunks = [text_out[i:i + 1900] for i in range(0, max(len(text_out), 1), 1900)]
        for i, chunk in enumerate(chunks):
            if not chunk:
                continue
            if followup is not None and i == 0:
                await followup.send(content=chunk)
            elif reply_to is not None and i == 0:
                await reply_to.reply(content=chunk, mention_author=False)
            else:
                await channel.send(content=chunk)

        for url in gif_urls:
            await channel.send(url)


class _null_ctx:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Conversation(bot))
