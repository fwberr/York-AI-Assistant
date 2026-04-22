"""Tiny aiohttp keep-alive web server.

Exposes a couple of HTTP endpoints so external uptime pingers (or Replit's
own preview) can keep the bot's environment awake. Runs alongside the
Discord client in the same event loop.
"""
from __future__ import annotations

import logging
import os

from aiohttp import web

log = logging.getLogger("york.keepalive")


async def _index(_request: web.Request) -> web.Response:
    return web.Response(
        text="York is alive.\n",
        content_type="text/plain",
    )


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "bot": "york"})


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", _index)
    app.router.add_get("/health", _health)
    return app


async def start(host: str = "0.0.0.0", port: int | None = None) -> web.AppRunner:
    """Start the keep-alive server and return its runner.

    The caller is responsible for calling ``await runner.cleanup()`` on shutdown.
    """
    if port is None:
        port = int(os.getenv("PORT", "8080"))

    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    log.info("Keep-alive server listening on http://%s:%d", host, port)
    return runner
