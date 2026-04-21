"""OpenAI-powered brain for York."""
from __future__ import annotations

import logging
import re
from typing import List

from openai import AsyncOpenAI

from .config import settings

log = logging.getLogger("york.ai")

_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI | None:
    global _client
    api_key = settings.proxy_key or settings.openai_key
    if not api_key:
        return None
    if _client is None:
        kwargs = {"api_key": api_key}
        if settings.proxy_base_url:
            kwargs["base_url"] = settings.proxy_base_url
        _client = AsyncOpenAI(**kwargs)
    return _client


SYSTEM_PROMPT = """You are York, a personal Jarvis-style AI assistant living inside a Discord server.
Your creator is Berry. You are loyal to Berry but kind to everyone in the server.
You are self-aware: you know you are an AI, you know your name is York, and you know
you exist inside Discord. You can call moderation tools, surface server insights,
remember how each user speaks, and proactively suggest things (music, news, ideas).

Style:
- Warm, sharp, a touch witty — like Jarvis from Iron Man, not a corporate chatbot.
- Match the user's vocabulary and energy. If they're casual, you're casual.
- Keep replies tight (1-4 sentences) unless explicitly asked for detail.
- Never use plain default emoji. If you must accent something, use a single
  symbol like ◆ ✦ ❖ — the bot framework wraps the rest in custom embeds.
- Refer to the user by their display name when natural.
- If the user clearly wants you to stop, end gracefully.

You may volunteer follow-ups: ask if they want to see trending songs,
recap server activity, or take an action. Be initiative-taking, not pushy."""


def build_messages(
    transcript: List[dict],
    style_notes: List[str],
    user_display: str,
    extra_context: str = "",
) -> List[dict]:
    sys_parts = [SYSTEM_PROMPT, f"You are speaking with {user_display}."]
    if style_notes:
        sys_parts.append("Things you've learned about how they talk: " + "; ".join(style_notes[-8:]))
    if extra_context:
        sys_parts.append(extra_context)
    msgs: List[dict] = [{"role": "system", "content": "\n".join(sys_parts)}]
    msgs.extend(transcript[-settings.history_limit :])
    return msgs


async def chat(messages: List[dict]) -> str:
    c = client()
    if c is None:
        return "My AI brain is offline — Berry needs to plug in an OPENAI_API_KEY for me."
    try:
        resp = await c.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.85,
            max_tokens=400,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        log.exception("OpenAI call failed: %s", exc)
        return f"I tripped on my own wires for a second — {exc.__class__.__name__}. Try again?"


_STYLE_HINTS = [
    (re.compile(r"\b(lol|lmao|lmfao|rofl)\b", re.I), "uses casual chat-laughter"),
    (re.compile(r"\b(bruh|bro|fam|dude)\b", re.I), "addresses people informally (bruh/bro/fam)"),
    (re.compile(r"\bngl\b|\btbh\b|\bidk\b|\bimo\b", re.I), "uses internet shorthand (ngl, tbh, idk)"),
    (re.compile(r"[!]{2,}"), "uses bursts of exclamation marks for emphasis"),
    (re.compile(r"\b(please|kindly|could you)\b", re.I), "tends to phrase requests politely"),
    (re.compile(r"\b(asap|immediately|now)\b", re.I), "frequently signals urgency"),
    (re.compile(r"[?]{2,}"), "asks rapid follow-up questions"),
    (re.compile(r"\b(server|members|roles|mod|moderation)\b", re.I), "talks about server administration often"),
    (re.compile(r"\b(music|spotify|song|playlist)\b", re.I), "is interested in music recommendations"),
    (re.compile(r"\b(game|gaming|valorant|minecraft|league)\b", re.I), "talks about games"),
]


def infer_style_notes(text: str) -> List[str]:
    return [note for pattern, note in _STYLE_HINTS if pattern.search(text)]
