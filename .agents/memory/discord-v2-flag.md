---
name: discord.py Components V2 flag name
description: The correct MessageFlags keyword for Components V2 messages in discord.py 2.7.1
---

In discord.py 2.7.1, the Components V2 message flag is:

```python
discord.MessageFlags(components_v2=True)   # CORRECT — value 32768 (1 << 15)
discord.MessageFlags(is_components_v2=True) # WRONG — raises TypeError at import time
```

**Why:** The flag method in discord.py's `MessageFlags` class is named `components_v2`, not `is_components_v2`. Because `_V2_FLAGS` is set at module level in `v2.py`, using the wrong name causes a `TypeError` the instant any cog imports `v2`, crashing every extension on startup.

**How to apply:** Any time Components V2 flags are constructed (in `v2.py`, `moderation.py`, `starboard.py`, `fun.py`, `economy.py`, `insights.py`, `help_cog.py`), always use `components_v2=True`.
