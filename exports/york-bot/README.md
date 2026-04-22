# York — Standalone Discord Bot

A Jarvis-style Discord bot. Built by Berry.

This package is the bot extracted from the workspace project, ready to
drop into a fresh Replit (or any Python host) and publish as a 24/7
Reserved VM.

## What's inside

```
york-bot/
├── main.py             # entrypoint -> python main.py
├── pyproject.toml      # dependencies (uv / pip / poetry compatible)
├── requirements.txt    # plain pip install -r requirements.txt
└── bot/                # the actual bot source
    ├── main.py
    ├── data/           # auto-created at runtime (memory + profiles)
    └── york/           # cogs, AI client, embeds, config, memory store
```

## Required secrets

Set these in your host's secrets / env vars:

- `DISCORD_BOT_TOKEN` — your bot's Discord token
- `OPENAI_API_KEY` — used for the AI conversation cog

## Run locally

```bash
pip install -r requirements.txt
export DISCORD_BOT_TOKEN=...   # or use a .env file
export OPENAI_API_KEY=...
python main.py
```

## Deploy on Replit (24/7)

1. Create a new **Python** Replit (not a workspace template).
2. Upload this whole folder, OR drag the `york-bot.zip` into the file pane and unzip.
3. In **Tools → Secrets**, add `DISCORD_BOT_TOKEN` and `OPENAI_API_KEY`.
4. Run command: `python main.py`
5. Click **Publish** → choose **Reserved VM** → Deploy.

## Talking to York

- Say `Hey York` (or `@York`) followed by anything to start a chat.
- Drop his name in passing and he'll wait for the channel to quiet, then chime in.
- Detach with: **enough**, **done**, **set free**, **detach**, or **goodbye**.

## Commands

Run `!help` in any channel for the full categorized menu — moderation,
server insights, social, economy, gambling (incl. blackjack), shop,
inventory, and marriage.
