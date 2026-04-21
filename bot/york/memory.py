"""Lightweight per-user / per-channel memory for York.

Stores:
* Conversation transcripts (so the AI can carry context).
* Active "attached" channels — channels where York is mid-conversation
  with a user and should keep replying without an explicit wake word.
* Learned style notes — short descriptors York infers from how the user
  speaks (vocabulary, tone, recurring topics).
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Dict, List, Tuple


@dataclass
class UserMemory:
    transcript: Deque[Dict[str, str]] = field(default_factory=lambda: deque(maxlen=24))
    style_notes: List[str] = field(default_factory=list)
    last_seen: float = 0.0


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._users: Dict[int, UserMemory] = defaultdict(UserMemory)
        # (channel_id, user_id) -> last-touched timestamp.
        # Each user has their own independent session in each channel,
        # so several people can talk to York at the same time.
        self._attachments: Dict[Tuple[int, int], float] = {}
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except Exception:
            return
        for uid, blob in raw.get("users", {}).items():
            mem = UserMemory()
            for msg in blob.get("transcript", []):
                mem.transcript.append(msg)
            mem.style_notes = blob.get("style_notes", [])
            mem.last_seen = blob.get("last_seen", 0.0)
            self._users[int(uid)] = mem
        for key, ts in raw.get("attachments", {}).items():
            try:
                cid_str, uid_str = key.split(":")
                self._attachments[(int(cid_str), int(uid_str))] = float(ts)
            except Exception:
                continue

    def save(self) -> None:
        with self._lock:
            data = {
                "users": {
                    str(uid): {
                        "transcript": list(mem.transcript),
                        "style_notes": mem.style_notes[-30:],
                        "last_seen": mem.last_seen,
                    }
                    for uid, mem in self._users.items()
                },
                "attachments": {
                    f"{cid}:{uid}": ts
                    for (cid, uid), ts in self._attachments.items()
                },
            }
            self.path.write_text(json.dumps(data, indent=2))

    # ---------- attachment (per channel + per user) ----------
    def attach(self, channel_id: int, user_id: int) -> None:
        self._attachments[(channel_id, user_id)] = time.time()
        self.save()

    def detach(self, channel_id: int, user_id: int) -> None:
        if self._attachments.pop((channel_id, user_id), None) is not None:
            self.save()

    def is_attached(self, channel_id: int, user_id: int) -> bool:
        ts = self._attachments.get((channel_id, user_id))
        if ts is None:
            return False
        # auto-detach after 20 minutes of silence
        if time.time() - ts > 20 * 60:
            self.detach(channel_id, user_id)
            return False
        return True

    def touch_attachment(self, channel_id: int, user_id: int) -> None:
        if (channel_id, user_id) in self._attachments:
            self._attachments[(channel_id, user_id)] = time.time()

    # ---------- transcript ----------
    def append_message(self, user_id: int, role: str, content: str) -> None:
        mem = self._users[user_id]
        mem.transcript.append({"role": role, "content": content})
        mem.last_seen = time.time()
        self.save()

    def transcript_for(self, user_id: int) -> List[Dict[str, str]]:
        return list(self._users[user_id].transcript)

    # ---------- style ----------
    def add_style_note(self, user_id: int, note: str) -> None:
        if not note:
            return
        mem = self._users[user_id]
        if note not in mem.style_notes:
            mem.style_notes.append(note)
            self.save()

    def style_notes_for(self, user_id: int) -> List[str]:
        return list(self._users[user_id].style_notes)

    # ---------- iter ----------
    def attached_channels(self) -> List[Tuple[int, int]]:
        return list(self._attachments.keys())

    def known_users(self) -> List[int]:
        return list(self._users.keys())
