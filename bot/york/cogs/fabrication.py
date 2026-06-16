"""Fabrication Lab — Jarvis-style holographic projection, rotation, and simulation."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import urllib.parse
from pathlib import Path
from typing import Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from .. import v2
from .. import ai as ai_module
from ..config import settings

log = logging.getLogger("york.fabrication")

# ---------------------------------------------------------------------------
# Simulation cache — same description always returns the same specs
# ---------------------------------------------------------------------------
_CACHE_FILE: Path = settings.data_dir / "fabrication_cache.json"


def _load_cache() -> dict[str, Any]:
    try:
        return json.loads(_CACHE_FILE.read_text())
    except Exception:
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    try:
        _CACHE_FILE.write_text(json.dumps(cache, indent=2))
    except Exception as exc:
        log.warning("Could not save fabrication cache: %s", exc)


def _cache_key(description: str) -> str:
    """Stable 16-char key for any description string."""
    normalised = description.lower().strip()
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
_HUD_SUFFIX = (
    "Stark Industries engineering schematic, electric blue holographic wireframe "
    "on pure black background, glowing neon lines, JARVIS HUD display overlay, "
    "sci-fi technical blueprint, particle energy effects, ultra-detailed"
)

_ROTATION_ANGLES = [
    ("FRONT VIEW",      "exact front-facing orthographic projection"),
    ("SIDE PROFILE",    "exact right-side profile, 90-degree orthographic"),
    ("3/4 PERSPECTIVE", "three-quarter isometric perspective"),
]


def _schematic_prompt(description: str, angle: str = "isometric 3D view") -> str:
    return (
        f"Precise holographic engineering schematic of {description}, "
        f"{angle}, {_HUD_SUFFIX}"
    )


# ---------------------------------------------------------------------------
# Image generation
#
# Provider chain (first available wins):
#   1. Together AI — FLUX.1-schnell-Free (genuinely free, just needs a free
#      API key from api.together.ai).  Set TOGETHER_API_KEY as a secret.
#   2. Cloudflare Workers AI — Flux-1-Schnell (free tier, 10k neurons/day).
#      Set CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN as secrets.
# ---------------------------------------------------------------------------

# ── Together AI ──────────────────────────────────────────────────────────────
_TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "")
_TOGETHER_URL     = "https://api.together.xyz/v1/images/generations"
_TOGETHER_MODEL   = "black-forest-labs/FLUX.1-schnell-Free"


async def _generate_via_together(prompt: str) -> discord.File | None:
    """Generate an image using Together AI FLUX.1-schnell-Free (free tier)."""
    headers = {
        "Authorization": f"Bearer {_TOGETHER_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":           _TOGETHER_MODEL,
        "prompt":          prompt,
        "width":           512,
        "height":          512,
        "steps":           4,
        "n":               1,
        "response_format": "b64_json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _TOGETHER_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning("Together AI returned %s: %s", resp.status, body[:300])
                    return None
                data = await resp.json(content_type=None)

        b64 = data.get("data", [{}])[0].get("b64_json", "")
        if not b64:
            log.warning("Together AI returned no image data")
            return None

        raw = base64.b64decode(b64)
        return discord.File(io.BytesIO(raw), filename="schematic.png")

    except Exception as exc:
        log.exception("Together AI image generation failed: %s", exc)
        return None


# ── Cloudflare Workers AI ────────────────────────────────────────────────────
_CF_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
_CF_API_TOKEN  = os.environ.get("CLOUDFLARE_API_TOKEN", "")
_CF_MODEL      = "@cf/black-forest-labs/flux-1-schnell"


async def _generate_via_cloudflare(prompt: str) -> discord.File | None:
    """Generate an image using Cloudflare Workers AI (Flux-1-Schnell)."""
    url = (
        f"https://api.cloudflare.com/client/v4/accounts"
        f"/{_CF_ACCOUNT_ID}/ai/run/{_CF_MODEL}"
    )
    headers = {
        "Authorization": f"Bearer {_CF_API_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {"prompt": prompt, "num_steps": 4}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning("Cloudflare AI returned %s: %s", resp.status, body[:200])
                    return None
                raw = await resp.read()
        return discord.File(io.BytesIO(raw), filename="schematic.png")
    except Exception as exc:
        log.exception("Cloudflare AI image generation failed: %s", exc)
        return None


# ── Public entry point ───────────────────────────────────────────────────────
async def _generate_image(prompt: str) -> discord.File | None:
    """Try Together AI first, then Cloudflare Workers AI."""
    if _TOGETHER_API_KEY:
        log.info("Using Together AI (FLUX.1-schnell-Free) for image generation")
        result = await _generate_via_together(prompt)
        if result is not None:
            return result
        log.warning("Together AI failed, trying Cloudflare")

    if _CF_ACCOUNT_ID and _CF_API_TOKEN:
        log.info("Using Cloudflare Workers AI (Flux-1-Schnell) for image generation")
        result = await _generate_via_cloudflare(prompt)
        if result is not None:
            return result
        log.warning("Cloudflare AI failed")

    log.error("No image provider succeeded — set TOGETHER_API_KEY to enable image generation")
    return None


# ---------------------------------------------------------------------------
# Simulation via LLM (structured JSON) — cached for consistency
# ---------------------------------------------------------------------------
_SIM_SYSTEM = (
    "You are York's internal fabrication AI. Return ONLY valid JSON — "
    "no markdown fences, no extra text."
)

_SIM_TEMPLATE = """\
Simulate the following design: "{description}"

Return this exact JSON structure:
{{
  "designation":          "<short code, e.g. MK-IX or WPN-03>",
  "classification":       "<type, e.g. Mark IX Combat Exosuit / Plasma Cannon>",
  "primary_material":     "<material, e.g. Titanium-Vibranium Composite>",
  "weight_kg":            <number>,
  "structural_integrity": <0.0-100.0>,
  "thermal_resistance_c": <integer>,
  "power_draw_kw":        <number with one decimal>,
  "combat_rating":        "<S / A+ / A / B / C>",
  "build_time_hours":     <number with one decimal>,
  "york_analysis":        "<one professional Jarvis-tone sentence assessing the design>"
}}
"""

# Module-level cache — loaded once at import, written after each new entry
_SIM_CACHE: dict[str, Any] = _load_cache()


async def _run_simulation(description: str) -> dict[str, Any] | None:
    key = _cache_key(description)

    # Return cached result if we already know this design
    if key in _SIM_CACHE:
        log.info("Fabrication cache hit for '%s'", description)
        return _SIM_CACHE[key]

    c = ai_module.client()
    if c is None:
        return None

    try:
        resp = await c.chat.completions.create(
            model=settings.ai_model,
            messages=[
                {"role": "system", "content": _SIM_SYSTEM},
                {"role": "user",   "content": _SIM_TEMPLATE.format(description=description)},
            ],
            max_tokens=400,
            temperature=0.1,   # low — minimises variation on first run
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(ln for ln in lines if not ln.startswith("```"))

        result = json.loads(raw)

        # Persist to disk so future calls return identical data
        _SIM_CACHE[key] = result
        _save_cache(_SIM_CACHE)
        return result

    except Exception as exc:
        log.exception("Simulation parse failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Simulation readout embed
# ---------------------------------------------------------------------------
def _sim_embed(data: dict[str, Any], description: str) -> discord.Embed:
    designation = data.get("designation", description[:20].upper())
    return v2.build(
        "info",
        f"◈  {designation} — Simulation Complete",
        data.get("york_analysis", "Simulation processed successfully."),
        fields=[
            ("Classification",       data.get("classification",      "—")),
            ("Primary Material",     data.get("primary_material",    "—")),
            ("Weight",               f"{data.get('weight_kg', '—')} kg"),
            ("Structural Integrity", f"{data.get('structural_integrity', '—')}%"),
            ("Thermal Resistance",   f"≤ {data.get('thermal_resistance_c', '—')} °C"),
            ("Power Draw",           f"{data.get('power_draw_kw', '—')} kW"),
            ("Combat Rating",        data.get("combat_rating", "—")),
            ("Est. Build Time",      f"{data.get('build_time_hours', '—')} hrs"),
        ],
        footer=f"Fabrication Lab · {settings.bot_name} · built by {settings.creator}",
    )


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class Fabrication(commands.Cog):
    """Jarvis-style holographic projection, rotation, and simulation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------ !project
    @commands.hybrid_command(
        name="project",
        description="Project a holographic schematic of any armor or weapon design.",
    )
    @app_commands.describe(description="What to project (e.g. 'Mark X repulsor gauntlet').")
    async def project(self, ctx: commands.Context, *, description: str):
        status = await v2.send(ctx, v2.info(
            "⬡  Holographic Array Online",
            f"Rendering schematic for: **{description}**\n"
            "-# Calibrating emitter grid — stand by (up to 60 s).",
        ))

        async with ctx.typing():
            file = await _generate_image(_schematic_prompt(description))

        if file is None:
            await v2.edit(status, v2.warn(
                "⬡  Array Offline",
                "Holographic projection is temporarily unavailable. Try again in a moment.",
            ))
            return

        await v2.edit(status, v2.success(
            "⬡  Schematic Projected",
            f"Holographic render of **{description}** is live.\n"
            "-# Use `!rotate` for multi-angle views · `!simulate` for full diagnostics.",
            footer=f"Fabrication Lab · {settings.bot_name} · built by {settings.creator}",
        ))
        await ctx.channel.send(file=file)

    # ------------------------------------------------------------------ !rotate
    @commands.hybrid_command(
        name="rotate",
        description="Rotate the hologram — front, side, and 3/4 perspective views.",
    )
    @app_commands.describe(description="What to rotate (same description as !project).")
    async def rotate(self, ctx: commands.Context, *, description: str):
        status = await v2.send(ctx, v2.info(
            "↻  Rotation Array Engaged",
            f"Three-view holographic rotation of: **{description}**\n"
            "-# Generating front, side, and 3/4 views — up to 90 seconds.",
        ))

        async with ctx.typing():
            tasks = [
                _generate_image(_schematic_prompt(description, angle=angle_desc))
                for _, angle_desc in _ROTATION_ANGLES
            ]
            renders = await asyncio.gather(*tasks)

        files_ready = [
            (label, f)
            for (label, _), f in zip(_ROTATION_ANGLES, renders)
            if f is not None
        ]

        if not files_ready:
            await v2.edit(status, v2.warn(
                "↻  Array Offline",
                "Holographic rotation is temporarily unavailable. Try again in a moment.",
            ))
            return

        await v2.edit(status, v2.success(
            "↻  Rotation Complete",
            f"All three projection angles of **{description}** rendered.",
            footer=f"Fabrication Lab · {settings.bot_name} · built by {settings.creator}",
        ))
        for label, file in files_ready:
            await ctx.channel.send(content=f"```╔══  {label}  ══╗```", file=file)

    # ------------------------------------------------------------------ !simulate
    @commands.hybrid_command(
        name="simulate",
        description="Run a full structural and combat simulation on a design.",
    )
    @app_commands.describe(description="Design to simulate (e.g. 'plasma railgun').")
    async def simulate(self, ctx: commands.Context, *, description: str):
        status = await v2.send(ctx, v2.info(
            "◈  Simulation Suite Initializing",
            f"Loading parameters for: **{description}**\n"
            "-# Running structural integrity, thermal, power, and combat diagnostics…",
        ))

        async with ctx.typing():
            data = await _run_simulation(description)

        if data is None:
            await v2.edit(status, v2.danger(
                "◈  Simulation Failure",
                "Diagnostic AI returned an error. Verify that the AI API key is set in Render.",
            ))
            return

        await v2.edit(status, _sim_embed(data, description))

    # ------------------------------------------------------------------ !fabricate
    @commands.hybrid_command(
        name="fabricate",
        description="Full Jarvis pipeline — holographic schematic + live simulation in parallel.",
    )
    @app_commands.describe(description="Full design to project and simulate.")
    async def fabricate(self, ctx: commands.Context, *, description: str):
        status = await v2.send(ctx, v2.info(
            "⬡  Fabrication Lab Online",
            f"Full diagnostic suite initiated for: **{description}**\n"
            "-# Projecting hologram and running simulation suite in parallel…",
        ))

        async with ctx.typing():
            file, sim_data = await asyncio.gather(
                _generate_image(_schematic_prompt(description)),
                _run_simulation(description),
            )

        has_image = file is not None
        has_sim   = sim_data is not None

        if not has_image and not has_sim:
            await v2.edit(status, v2.danger(
                "⬡  Fabrication Lab Offline",
                "Both image generation and AI diagnostics are unavailable.\n"
                "Verify that your AI API key is set in Render environment variables.",
            ))
            return

        designation = (
            sim_data.get("designation", description[:20].upper())
            if sim_data else description[:20].upper()
        )

        await v2.edit(status, v2.success(
            f"⬡  {designation} — Fabrication Complete",
            "Holographic schematic rendered. Simulation data follows.",
            footer=f"Fabrication Lab · {settings.bot_name} · built by {settings.creator}",
        ))

        if has_image:
            await ctx.channel.send(file=file)

        if has_sim:
            await ctx.channel.send(embed=_sim_embed(sim_data, description))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fabrication(bot))
