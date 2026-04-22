"""Entrypoint for the York Discord bot.

Just re-exports the existing bot package so the deployment run command
can stay simple: `python main.py`.
"""
from bot.main import main
import asyncio

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
