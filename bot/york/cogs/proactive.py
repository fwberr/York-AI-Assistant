"""Proactive cog — York volunteers messages on his own.

Every so often, York looks at recent activity in attached / favourite channels
and sends an unprompted suggestion: a question, an idea, a recommendation.
"""
from __future__ import annotations

import asyncio
import logging
import random

import discord
from discord.ext import commands, tasks

from .. import ai, embeds
from ..config import settings

log = logging.getLogger("york.proactive")

PROMPTS = [
    "Pick one user you've been chatting with and ask them a thoughtful, short question to keep the conversation going.",
    "Recommend a fresh idea or activity to the user — could be a Spotify trending playlist, a small productivity hack, or a fun server game.",
    "Offer a tiny, specific compliment or observation about how the user has been talking lately.",
    "Suggest a small server-improvement idea (like a new channel topic, a poll, or a fun event) — frame it as a question.",
    "Drop a quick, intriguing fact or 'did you know' line tailored to what the user seems to like.",
]


class Proactive(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    @tasks.loop(minutes=1)
    async def loop(self):
        # randomised cadence — only fire occasionally
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
            extra_context=f"You are about to send an UNPROMPTED message to {user.display_name} in #{channel.name}. {prompt}",
        )
        # add a final 'user' instruction so the model speaks
        msgs.append({"role": "user", "content": prompt})
        text = await ai.chat(msgs)
        if not text:
            return
        self.bot.memory.append_message(user_id, "assistant", text)
        try:
            await channel.send(
                content=f"{user.mention}",
                embed=embeds.info(f"{settings.emoji.spark}  Hey, just a thought…", text),
            )
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Proactive(bot))
