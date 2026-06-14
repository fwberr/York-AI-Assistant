---
name: discord.py 2.7.1 Components V2 correct API
description: Correct constructor signatures for all Components V2 classes in discord.py 2.7.1
---

## Flag name
```python
discord.MessageFlags(components_v2=True)   # CORRECT — value 32768 (1 << 15)
discord.MessageFlags(is_components_v2=True) # WRONG — raises TypeError
```

## Component constructors (all verified against discord.py 2.7.1 source)

```python
# Container — children are POSITIONAL, kwargs are keyword-only
discord.ui.Container(*items, accent_colour=int_or_Colour, spoiler=False)

# Section — children positional, accessory= is REQUIRED keyword
discord.ui.Section(text_display, accessory=thumbnail_or_button)
# If no accessory needed, use TextDisplay directly — Section without accessory crashes

# TextDisplay
discord.ui.TextDisplay("markdown content")

# Separator — no 'divider' param; spacing and visible only
discord.ui.Separator(spacing=discord.SeparatorSpacing.small)  # or .large

# Thumbnail — first positional arg is media URL/File, NOT url= kwarg
discord.ui.Thumbnail("https://...")
```

## Common mistakes
- `Section(components=[item])` → TypeError (no `components` kwarg)
- `Separator(divider=True)` → TypeError (no `divider` kwarg)
- `Thumbnail(url="...")` → TypeError (no `url` kwarg, use positional)
- Smart/curly quotes `"..."` in source → SyntaxError on Python 3.14

## Build pattern (use constructor, not add_item)
```python
items = [TextDisplay("## Title"), Separator(), TextDisplay("body")]
container = discord.ui.Container(*items, accent_colour=0x6E5BFF)
```

**Why:** The `add_item` method exists on View but Container in 2.7.1 prefers the constructor pattern. Using it avoids API drift.
