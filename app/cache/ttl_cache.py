"""In-memory TTL + LRU caches.

Everything a request produces lives in process memory and disappears when the TTL
lapses, which is what "privacy by design" means here: no uploaded lease is ever
written to persistent storage. The cache enforces both an entry limit and a byte
budget so a burst of large PDFs cannot exhaust the heap.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class _Entry(Generic[V]):
    value: V
    expires_at: float
    size: int = 0


class TTLCache(Generic[K, V]):
    """Thread-safe TTL cache with LRU eviction and an optional byte budget."""

    def __init__(
        self,
        *,
        max_entries: int = 64,
        ttl_seconds: float = 3600,
        max_bytes: int | None = None,
    ) -> None:
        self.max_entries = max(1, max_entries)
        self.ttl_seconds = max(0, ttl_seconds)
        self.max_bytes = max_bytes
        self._entries: dict[K, _Entry[V]] = {}
        self._total_bytes = 0
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    # -- public API ---------------------------------------------------------
    def set(self, key: K, value: V, *, size: int = 0, ttl_seconds: float | None = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        with self._lock:
            existing = self._entries.pop(key, None)
            if existing is not None:
                self._total_bytes -= existing.size
            self._entries[key] = _Entry(
                value=value,
                expires_at=time.monotonic() + ttl if ttl > 0 else float("inf"),
                size=max(0, size),
            )
            self._total_bytes += max(0, size)
            self._evict()

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return None
            if _is_expired(entry):
                self._delete(key, entry)
                self.misses += 1
                return None
            self.hits += 1
            # LRU: reinsert at the end of the insertion-ordered dict.
            self._entries.pop(key)
            self._entries[key] = entry
            return entry.value

    def delete(self, key: K) -> bool:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            self._delete(key, entry)
            return True

    def purge_expired(self) -> int:
        with self._lock:
            expired = [key for key, entry in self._entries.items() if _is_expired(entry)]
            for key in expired:
                entry = self._entries.pop(key)
                self._total_bytes -= entry.size
            return len(expired)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._total_bytes = 0

    # -- introspection ------------------------------------------------------
    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def __contains__(self, key: object) -> bool:
        return self.get(key) is not None  # type: ignore[arg-type]

    def __iter__(self) -> Iterator[K]:
        with self._lock:
            return iter(list(self._entries))

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
                "total_bytes": self._total_bytes,
                "max_bytes": self.max_bytes,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
            }

    # -- internals ----------------------------------------------------------
    def _delete(self, key: K, entry: _Entry[V]) -> None:
        self._entries.pop(key, None)
        self._total_bytes -= entry.size

    def _evict(self) -> None:
        while self._entries and (
            len(self._entries) > self.max_entries
            or (self.max_bytes is not None and self._total_bytes > self.max_bytes)
        ):
            oldest_key = next(iter(self._entries))
            oldest = self._entries.pop(oldest_key)
            self._total_bytes -= oldest.size
            self.evictions += 1


def _is_expired(entry: _Entry[Any]) -> bool:
    return entry.expires_at < time.monotonic()
