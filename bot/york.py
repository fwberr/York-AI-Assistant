"""York - A Jarvis-like Discord bot.

Created by Berry. York lives in your server, listens for the wake phrase
"Hey York", chats with AI intelligence, runs moderation, and proactively
volunteers ideas, suggestions and questions of his own.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands

from york.config import settings
from york.keepalive import start as start_keepalive
from york.memory import MemoryStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("york")


class York(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,
            description="York — your in-server Jarvis. Created by Berry.",
        )
        self.memory = MemoryStore(Path("bot/data/memory.json"))

    async def setup_hook(self) -> None:
        for ext in (
            "york.cogs.conversation",
            "york.cogs.moderation",
            "york.cogs.insights",
            "york.cogs.fun",
            "york.cogs.proactive",
            "york.cogs.help_cog",
        ):
            try:
                await self.load_extension(ext)
                log.info("Loaded extension: %s", ext)
            except Exception as exc:  # noqa: BLE001
                log.exception("Failed to load %s: %s", ext, exc)
        try:
            synced = await self.tree.sync()
            log.info("Synced %d slash commands", len(synced))
        except Exception as exc:  # noqa: BLE001
            log.warning("Slash sync failed: %s", exc)

    async def on_ready(self) -> None:
        log.info("York online as %s (id=%s)", self.user, self.user.id if self.user else "?")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name='for "Hey York" — built by Berry',
            ),
            status=discord.Status.online,
        )


async def main() -> None:
    if not settings.discord_token:
        log.error("DISCORD_BOT_TOKEN is missing. Add it as a secret and restart.")
        sys.exit(1)
    if not settings.openai_key:
        log.warning("OPENAI_API_KEY missing — AI conversation will be disabled.")

    keepalive_runner = await start_keepalive()

    bot = York()
    try:
        async with bot:
            await bot.start(settings.discord_token)
    finally:
        await keepalive_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
