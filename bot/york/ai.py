"""AI brain for York.

Primary provider: Google Gemini 2.0 Flash (GEMINI_API_KEY) — called via
the native Gemini REST API directly with aiohttp (no OpenAI SDK layer).
Fallback: Groq (aiohttp, Render IPs are blocked by Groq's SDK path),
then Replit proxy / OpenAI via the OpenAI SDK.
"""
from __future__ import annotations

import logging
import re
from typing import List

import aiohttp
from openai import AsyncOpenAI

from .config import settings

log = logging.getLogger("york.ai")

_client: AsyncOpenAI | None = None

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_AIOHTTP_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _is_gemini() -> bool:
    return "googleapis.com" in (settings.ai_url or "")


def _is_groq() -> bool:
    return "groq.com" in (settings.ai_url or "")


async def _gemini_chat(messages: List[dict], model: str, max_tokens: int) -> str:
    """Call Gemini native REST API directly — avoids the OpenAI compat layer."""
    # Split system message from conversation turns
    system_text = ""
    contents = []
    for m in messages:
        role = m.get("role", "")
        text = m.get("content", "")
        if role == "system":
            system_text = text
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})
        else:
            contents.append({"role": "user", "parts": [{"text": text}]})

    payload: dict = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if system_text:
        payload["system_instruction"] = {"parts": [{"text": system_text}]}

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models"
        f"/{model}:generateContent?key={settings.ai_key}"
    )
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                err = data.get("error", {}).get("message", str(data))
                raise RuntimeError(f"Gemini {resp.status}: {err}")
            return (
                data["candidates"][0]["content"]["parts"][0]["text"] or ""
            ).strip()


async def _groq_chat(messages: List[dict], model: str, max_tokens: int) -> str:
    """Call Groq directly via aiohttp, bypassing the openai SDK / httpx stack."""
    headers = {**_AIOHTTP_HEADERS, "Authorization": f"Bearer {settings.ai_key}"}
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        async with session.post(_GROQ_URL, json=payload) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                err = data.get("error", {}).get("message", str(data))
                raise RuntimeError(f"Groq {resp.status}: {err}")
            return (data["choices"][0]["message"]["content"] or "").strip()


def client() -> AsyncOpenAI | None:
    global _client
    if _is_gemini() or _is_groq():
        return None  # These use aiohttp paths instead
    key = settings.ai_key
    if not key:
        return None
    if _client is None:
        kwargs: dict = {"api_key": key}
        if settings.ai_url:
            kwargs["base_url"] = settings.ai_url
        _client = AsyncOpenAI(**kwargs)
    return _client


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
- You may include ONE anime reaction GIF token when it genuinely fits.
- Format: `[gif:WORD]` where WORD is a SINGLE word from the allowed list below.
  Never put a character name or extra words inside the brackets — only the action.
  Correct: `[gif:wink]`  Wrong: `[gif:astolfo wink]`  Wrong: `[gif:happy smile]`
- Allowed actions: baka, bite, blush, bored, cry, cuddle, dance, facepalm, feed,
  handhold, happy, highfive, hug, kick, kiss, laugh, nod, nom, nope, pat, peck,
  poke, pout, punch, run, shoot, shrug, sleep, slap, smile, smug, stare, think,
  thumbsup, tickle, wave, wink, yawn, yeet.
- Most replies need no GIF. Only include one when it genuinely fits the emotion.

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
    if not settings.ai_key:
        return (
            "My AI module is currently offline. "
            "Set MISTRAL_API_KEY in your environment variables."
        )
    try:
        # Gemini: native REST API via aiohttp — no OpenAI compat layer.
        if _is_gemini():
            return await _gemini_chat(messages, settings.ai_model, 600)

        # Groq: aiohttp directly to avoid 403 on cloud-hosted environments.
        if _is_groq():
            return await _groq_chat(messages, settings.ai_model, 600)

        # OpenAI / other providers: use the SDK.
        c = client()
        if c is None:
            return "My AI module is currently offline."
        resp = await c.chat.completions.create(
            model=settings.ai_model,
            messages=messages,
            max_completion_tokens=600,
        )
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
