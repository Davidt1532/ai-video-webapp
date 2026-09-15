"""Rotating pool of NovAI API keys.

NovAI's free video model caps each key at FREE_DAILY_VIDEO_LIMIT generations
per day (reset at midnight UTC+8). The pool hands out keys round-robin, counts
submissions against each key's daily quota, and marks a key exhausted when the
provider reports the daily limit has been hit. When every key is exhausted,
jobs fail fast with a clear message instead of retrying uselessly for minutes.

Usage:
    from key_pool import key_pool
    key = key_pool.get_video_key()   # -> "nvai-..." or None
    key_pool.mark_submitted(key)     # counts 1 generation
    key_pool.mark_exhausted(key)     # forced exhaustion (provider 429)
    any_key = key_pool.any_key()     # first key (chat calls, not video)

Thread-safe; pools are small so a simple lock suffices.
"""
import threading
from datetime import datetime, timedelta

from config import (
    VIDEO_API_KEY, VIDEO_API_KEYS, FREE_DAILY_VIDEO_LIMIT, QUOTA_OFFSET_HOURS,
)


def _parse_keys() -> list[str]:
    """Load keys from VIDEO_API_KEYS (comma-separated), falling back to VIDEO_API_KEY."""
    keys = []
    if VIDEO_API_KEYS:
        keys = [k.strip() for k in VIDEO_API_KEYS.split(",") if k.strip()]
    if not keys and VIDEO_API_KEY:
        keys = [VIDEO_API_KEY.strip()]
    return keys


class KeyPool:
    """Round-robin pool tracking per-key daily generation quota."""

    def __init__(self, keys: list[str] = None, daily_limit: int = None,
                 offset_hours: int = None):
        self._keys = keys if keys is not None else _parse_keys()
        self._limit = daily_limit if daily_limit is not None else FREE_DAILY_VIDEO_LIMIT
        self._offset = offset_hours if offset_hours is not None else QUOTA_OFFSET_HOURS
        self._lock = threading.Lock()
        self._used = {k: 0 for k in self._keys}
        self._exhausted = {k: False for k in self._keys}
        self._day = self._current_day()
        self._cursor = 0

    # ---------- internals ----------
    def _current_day(self) -> str:
        return (datetime.utcnow() + timedelta(hours=self._offset)).date().isoformat()

    def _reset_if_new_day(self):
        today = self._current_day()
        if today != self._day:
            self._day = today
            self._used = {k: 0 for k in self._keys}
            self._exhausted = {k: False for k in self._keys}

    def _available(self):
        self._reset_if_new_day()
        return [k for k in self._keys if self._used[k] < self._limit and not self._exhausted[k]]

    # ---------- public API ----------
    def get_video_key(self) -> str:
        """Return the next usable key for video generation, or None if all are spent."""
        with self._lock:
            avail = self._available()
            if not avail:
                return None
            for _ in range(len(self._keys)):
                key = self._keys[self._cursor % len(self._keys)]
                self._cursor += 1
                if key in avail:
                    return key
            return avail[0]

    def mark_submitted(self, key: str):
        """Record one video generation submission against a key's daily quota."""
        with self._lock:
            if key in self._used:
                self._used[key] += 1

    def mark_exhausted(self, key: str):
        """Mark a key as spent for the day (provider reported the daily limit)."""
        with self._lock:
            if key in self._exhausted:
                self._exhausted[key] = True

    def any_key(self) -> str:
        """First key regardless of video quota (chat calls have a separate quota)."""
        with self._lock:
            self._reset_if_new_day()
            return self._keys[0] if self._keys else ""

    def status(self) -> list[dict]:
        """Per-key usage summary (no secrets)."""
        with self._lock:
            self._reset_if_new_day()
            return [
                {
                    "index": i,
                    "prefix": key[:8] + "..." if key else "",
                    "used": self._used.get(key, 0),
                    "limit": self._limit,
                    "exhausted": self._exhausted.get(key, False),
                }
                for i, key in enumerate(self._keys)
            ]

    def all_exhausted_message(self) -> str:
        n = len(self._keys)
        return (f"All {n} NovAI API key(s) reached the daily free limit "
                f"({self._limit} video generations each). Resume after midnight "
                f"(UTC+{self._offset}) or add a paid model key.")


key_pool = KeyPool()


if __name__ == "__main__":
    import os
    os.environ.setdefault("VIDEO_API_KEYS", "demo-a,demo-b,demo-c")
    pool = KeyPool(["demo-a", "demo-b", "demo-c"], daily_limit=2)
    for i in range(7):
        key = pool.get_video_key()
        print(f"get -> {key}")
        if key:
            pool.mark_submitted(key)
    print("status:", pool.status())
    print(pool.all_exhausted_message())