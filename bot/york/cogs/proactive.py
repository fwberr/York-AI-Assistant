"""Proactive cog — York volunteers messages on his own occasionally."""
from __future__ import annotations

import asyncio
import logging
import random
import re

import discord
from discord.ext import commands, tasks

from .. import ai
from ..config import settings

log = logging.getLogger("york.proactive")

_MASS_PING = re.compile(r"@(?:everyone|here)", re.IGNORECASE)

PROMPTS = [
    "Ask the user a short, thoughtful question to keep the conversation going.",
    "Recommend something useful or interesting — a tip, a tool, or a fun idea tailored to what they talk about.",
    "Share a brief, specific observation about the server or a recent topic.",
    "Suggest a small server-improvement idea, framed as a polite question.",
    "Drop a concise, intriguing fact related to something the user seems interested in.",
]


class Proactive(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    @tasks.loop(minutes=1)
    async def loop(self):
        if random.randint(0, settings.proactive_max_minutes) > settings.proactive_min_minutes:
            return
        await self._maybe_speak()

    @loop.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(60)

    async def _maybe_speak(self):
        attached = self.bot.memory.attached_channels()
        if not attached:
            return
        channel_id, user_id = random.choice(attached)
        channel = self.bot.get_channel(channel_id)
        if channel is None or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        try:
            user = await self.bot.fetch_user(user_id)
        except Exception:
            return
        prompt = random.choice(PROMPTS)
        msgs = ai.build_messages(
            self.bot.memory.transcript_for(user_id),
            self.bot.memory.style_notes_for(user_id),
            getattr(user, "display_name", str(user)),
            extra_context=(
                f"You are sending an UNPROMPTED message to {user.display_name} in #{channel.name}. "
                f"Keep it brief — one or two sentences. {prompt}"
            ),
        )
        msgs.append({"role": "user", "content": prompt})
        text = await ai.chat(msgs)
        if not text:
            return
        # Strip mass pings from proactive messages too.
        text = _MASS_PING.sub(lambda m: m.group(0).replace("@", "@ "), text)
        self.bot.memory.append_message(user_id, "assistant", text)
        try:
            await channel.send(content=f"{user.mention} — {text}")
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Proactive(bot))
