"""
In-memory per-browser state store.

The signed session cookie keeps only small values (token, username, state id),
while the id of the last generated answer lives here.
"""

import threading
import time
import uuid
from typing import Any

from starlette.requests import Request

STATE_ID_SESSION_KEY = "state_id"
LAST_QUERY_RESPONSE_ID = "last_query_response_id"
# Options of the last search (the sidebar is filled with them again)
LAST_SEARCH_PARAMS = "last_search_params"
# Searches whose generative answer is fetched after the results are shown
PENDING_GENERATIONS = "pending_generations"


class StateStore:
    def __init__(self, ttl_seconds: int = 8 * 3600, max_entries: int = 2000) -> None:
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[str, tuple[float, dict]] = {}

    def get(self, state_id: str) -> dict:
        with self._lock:
            entry = self._entries.get(state_id)
            if entry is None:
                return {}
            stored_at, state = entry
            if time.time() - stored_at > self._ttl_seconds:
                self._entries.pop(state_id, None)
                return {}
            # Refresh the timestamp, the session is still active.
            self._entries[state_id] = (time.time(), state)
            return state

    def update(self, state_id: str, **values: Any) -> dict:
        with self._lock:
            self._drop_expired()
            state = dict(self._entries.get(state_id, (time.time(), {}))[1])
            state.update(values)
            self._entries[state_id] = (time.time(), state)
            self._drop_oldest()
            return state

    def clear(self, state_id: str) -> None:
        with self._lock:
            self._entries.pop(state_id, None)

    def _drop_expired(self) -> None:
        now = time.time()
        for state_id in [
            key
            for key, (stored_at, _) in self._entries.items()
            if now - stored_at > self._ttl_seconds
        ]:
            self._entries.pop(state_id, None)

    def _drop_oldest(self) -> None:
        while len(self._entries) > self._max_entries:
            oldest = min(self._entries, key=lambda key: self._entries[key][0])
            self._entries.pop(oldest, None)


STATE_STORE = StateStore()


def get_state_id(request: Request) -> str:
    state_id = request.session.get(STATE_ID_SESSION_KEY)
    if not state_id:
        state_id = uuid.uuid4().hex
        request.session[STATE_ID_SESSION_KEY] = state_id
    return state_id


def get_state(request: Request) -> dict:
    return STATE_STORE.get(get_state_id(request))


def set_state(request: Request, **values: Any) -> dict:
    return STATE_STORE.update(get_state_id(request), **values)


def clear_state(request: Request) -> None:
    STATE_STORE.clear(get_state_id(request))
