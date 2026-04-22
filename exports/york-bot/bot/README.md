# York

A Jarvis-style Discord bot. Built by Berry.

## Run

Token + key live in Replit secrets:
- `DISCORD_BOT_TOKEN`
- `OPENAI_API_KEY`

Workflow `York Bot` runs `python bot/main.py`.

## How to talk to York

- Say `Hey York` followed by anything to start a conversation.
- Mention `@York` to wake him too.
- While he's "attached", he replies to every following message of yours
  without needing the wake word again — and may speak up on his own.
- To detach him say one of: **enough**, **done**, **set free**, **detach**, **goodbye**.

## Custom emoji

Every accent glyph (`◆ ✦ ❖ ⚒ ◑ ◐ ♛ ✺`) can be swapped for a real custom
emoji from your server. Just set the matching env var in `bot/york/config.py`
to e.g. `<:york_ok:123456789012345678>` and restart.
