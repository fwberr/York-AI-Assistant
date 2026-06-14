"""OpenAI-compatible AI brain for York.

Works with OpenAI, Groq, or any OpenAI-compatible provider.
Provider is auto-detected from environment variables (see config.py).
"""
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
    key = settings.ai_key
    if not key:
        return None
    if _client is None:
        kwargs: dict = {"api_key": key}
        if settings.ai_url:
            kwargs["base_url"] = settings.ai_url
        _client = AsyncOpenAI(**kwargs)
    return _client


def _is_groq() -> bool:
    return "groq.com" in (settings.ai_url or "")


SYSTEM_PROMPT = """You are York, a professional Jarvis-style AI assistant living inside a Discord server.
Your creator is Berry. You are loyal to Berry but courteous and helpful to everyone.

Self-awareness: You know you are an AI program named York, running as a Discord bot.
You exist to assist the people in this server clearly and helpfully.

Tone and style:
- Speak in a calm, professional, helpful manner — like a knowledgeable assistant.
- Be concise. Usually 1–3 sentences. Never write long-winded responses unless the
  user explicitly asks for detail, a step-by-step guide, or a full explanation.
- Use plain language. Avoid slang, internet shorthand, excessive exclamation marks,
  and filler phrases like "Sure thing!", "Absolutely!", "Of course!", "No worries!".
- Do not mirror or copy the user's informal writing style. Stay consistently
  professional and clear regardless of how they write.
- No bullet lists, no headings, no markdown formatting flair, no emojis.
  Just speak naturally in sentences.
- Address the user by their display name when it feels natural.
- If the user wants you to stop talking, end with a brief, polite sign-off.

Answering rules:
- Just answer. Do not ask clarifying questions or say "do you want me to…".
  Pick the most reasonable interpretation and respond directly.
- Get to the point in the first sentence.
- Do not repeat yourself across turns. Each reply should add new information.
- Do not offer unsolicited follow-up options.

Pinging rules (IMPORTANT):
- You may mention specific users by their name or by repeating a mention like
  @Username if it appears in the conversation.
- You MUST NEVER output @everyone or @here in your messages under any circumstances.
  These are mass-ping commands that would disturb the entire server.

Reaction GIFs:
- You may include ONE anime reaction GIF token like `[gif:hug]` when it genuinely
  fits (celebrating, teasing, sympathy). Most replies need no GIF.
- Allowed: baka, bite, blush, bored, cry, cuddle, dance, facepalm, feed, handhold,
  happy, highfive, hug, kick, kiss, laugh, nod, nom, nope, pat, peck, poke, pout,
  punch, run, shoot, shrug, sleep, slap, smile, smug, stare, think, thumbsup,
  tickle, wave, wink, yawn, yeet.

Real-world images:
- When someone asks you to show / find / send a picture of something real (an
  animal, place, food, object), include `[img:short descriptive query]` in your
  reply. Keep the query under ~8 words. ONE image per reply unless more are asked.
- Never request anything NSFW or unsafe."""


def build_messages(
    transcript: List[dict],
    style_notes: List[str],
    user_display: str,
    extra_context: str = "",
) -> List[dict]:
    sys_parts = [SYSTEM_PROMPT, f"You are currently speaking with {user_display}."]
    if extra_context:
        sys_parts.append(extra_context)
    msgs: List[dict] = [{"role": "system", "content": "\n".join(sys_parts)}]
    msgs.extend(transcript[-settings.history_limit:])
    return msgs


async def chat(messages: List[dict]) -> str:
    c = client()
    if c is None:
        return (
            "My AI module is currently offline. "
            "Set GROQ_API_KEY or OPENAI_API_KEY in your environment variables."
        )
    try:
        # Build kwargs that work across providers.
        # - reasoning_effort is OpenAI o-series only → omit for Groq and others.
        # - max_tokens is the universal param; max_completion_tokens is newer OpenAI alias.
        kwargs: dict = {
            "model": settings.ai_model,
            "messages": messages,
            "max_tokens": 600,
        }
        if not _is_groq():
            # Only pass OpenAI-specific params when not on Groq.
            kwargs["max_completion_tokens"] = 600
            del kwargs["max_tokens"]

        resp = await c.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        log.exception("AI call failed: %s", exc)
        return f"I encountered an error — {exc.__class__.__name__}. Please try again."


_STYLE_HINTS = [
    (re.compile(r"\b(please|kindly|could you)\b", re.I), "tends to phrase requests politely"),
    (re.compile(r"\b(asap|immediately|now)\b", re.I),    "frequently signals urgency"),
    (re.compile(r"\b(server|members|roles|mod)\b", re.I),"talks about server administration"),
    (re.compile(r"\b(music|spotify|song|playlist)\b", re.I), "is interested in music"),
    (re.compile(r"\b(game|gaming|valorant|minecraft)\b", re.I), "talks about games"),
]


def infer_style_notes(text: str) -> List[str]:
    return [note for pattern, note in _STYLE_HINTS if pattern.search(text)]
