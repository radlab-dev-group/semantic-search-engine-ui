"""Client for the semantic-search-engine backend API.

All calls go out from the frontend server: the backend has no CORS, and the token stays on the
server side. The client unpacks the `{status, body}` envelope and turns errors into `ApiError`
with a kind that the interface can show the employee (session, no access, timeout, unavailable).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings

log = logging.getLogger("ui.api")


class ApiError(Exception):
    """Backend call error.

    kind: auth | forbidden | timeout | unavailable | not_found | backend
    """

    def __init__(self, kind: str, status: int = 0, code: str = "", message: str = "") -> None:
        super().__init__(f"{kind} {status} {code} {message}".strip())
        self.kind = kind
        self.status = status
        self.code = code
        self.message = message


class ApiClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        base = settings.api_host + (f"/{settings.api_prefix}" if settings.api_prefix else "")
        self._client = httpx.AsyncClient(
            base_url=base,
            verify=settings.verify_tls,
            timeout=settings.timeout_default,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "radlab-rag-ui/0.1"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def call(
        self,
        method: str,
        endpoint: str,
        *,
        token: str | None = None,
        lang: str = "pl",
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Calls an endpoint (name from the `ep` section of the configuration) and returns `body`."""
        path = self.settings.ep(endpoint)
        headers = {"Authorization": f"Token {token}"} if token else {}
        if method == "GET":
            params = {**(params or {}), "lang": lang}
        else:
            json = {**(json or {}), "lang": lang}
        try:
            response = await self._client.request(
                method,
                f"/{path}",
                params={k: v for k, v in (params or {}).items() if v is not None} or None,
                json=json,
                headers=headers,
                timeout=timeout or self.settings.timeout_default,
            )
        except httpx.TimeoutException as exc:
            raise ApiError("timeout", message=str(exc)) from exc
        except httpx.TransportError as exc:
            raise ApiError("unavailable", message=str(exc)) from exc

        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.status_code >= 400:
            code, message = _first_error(payload)
            log.warning("API %s %s → %s %s", method, path, response.status_code, code or message)
            if response.status_code == 401:
                raise ApiError("auth", 401, code, message)
            if response.status_code == 403:
                raise ApiError("forbidden", 403, code, message)
            if response.status_code == 404:
                raise ApiError("not_found", 404, code, message)
            if response.status_code in (502, 503, 504):
                raise ApiError("unavailable", response.status_code, code, message)
            raise ApiError("backend", response.status_code, code, message)

        if isinstance(payload, dict) and "status" in payload:
            if payload["status"] is True:
                return payload.get("body")
            code, message = _first_error(payload)
            raise ApiError("backend", response.status_code, code, message)
        # Endpoints without an envelope (local `login` returns {"token": "..."}).
        return payload


def _first_error(payload: Any) -> tuple[str, str]:
    if isinstance(payload, dict):
        errors = payload.get("errors") or []
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            first = errors[0]
        # Backend: {"error_code": "e__data_502", "message": "<text in the lang language>"}
            code = first.get("error_code") or first.get("code") or ""
            return str(code), str(first.get("message") or first.get("msg") or "")
        if "detail" in payload:
            return "", str(payload["detail"])
    return "", ""
