"""Frontend-server memory for data the backend does not return in history.

- answer sources and footnotes (until CR-04),
- the knowledge base and document scope of a conversation (until CR-05 and CR-18).

By default this is in-process memory with the lifetime of a session. With several frontend processes
the implementation must be replaced by a shared one (e.g. Redis) – the `SessionStore` interface is
ready for that.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Protocol


class SessionStore(Protocol):
    def put(self, sid: str, key: str, value: Any) -> None: ...
    def get(self, sid: str, key: str, default: Any = None) -> Any: ...
    def drop(self, sid: str) -> None: ...


class MemoryStore:
    def __init__(self, ttl_s: int = 8 * 3600, max_sessions: int = 5000) -> None:
        self.ttl_s = ttl_s
        self.max_sessions = max_sessions
        self._data: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def _bucket(self, sid: str) -> dict[str, Any]:
        now = time.monotonic()
        entry = self._data.get(sid)
        if entry is None or now - entry[0] > self.ttl_s:
            entry = (now, {})
        self._data[sid] = (now, entry[1])
        if len(self._data) > self.max_sessions:
            self._evict(now)
        return entry[1]

    def _evict(self, now: float) -> None:
        expired = [k for k, (t, _) in self._data.items() if now - t > self.ttl_s]
        for k in expired:
            self._data.pop(k, None)
        while len(self._data) > self.max_sessions:
            oldest = min(self._data, key=lambda k: self._data[k][0])
            self._data.pop(oldest, None)

    def put(self, sid: str, key: str, value: Any) -> None:
        with self._lock:
            self._bucket(sid)[key] = value

    def get(self, sid: str, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._bucket(sid).get(key, default)

    def drop(self, sid: str) -> None:
        with self._lock:
            self._data.pop(sid, None)
