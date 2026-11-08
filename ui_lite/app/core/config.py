"""Konfiguracja frontendu.

Plik JSON zgodny z `ui-configuration.json` obecnego UI RadLab (sekcja `api_hosts`),
rozszerzony o sekcje `auth`, `ui`, `timeouts`, `defaults`, `formats` i `features`.
Ścieżka pliku: zmienna `UI_CONFIG` (domyślnie `configs/ui-configuration.json`).
Zmienne środowiskowe nadpisują wybrane pola, żeby RadLab mógł wdrożyć obraz bez edycji pliku.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "configs" / "ui-configuration.json"
EXAMPLE_PATH = ROOT / "configs" / "ui-configuration.example.json"


@dataclass
class Settings:
    raw: dict[str, Any]
    api_host: str
    api_prefix: str
    verify_tls: bool
    endpoints: dict[str, str]
    auth_mode: str
    sso_button: bool
    default_language: str
    languages: list[str]
    brand: str
    history_limit: int
    timeout_default: float
    timeout_answer: float
    options: dict[str, Any]
    search_options: dict[str, Any]
    preview_pages: int
    citation_instruction: str
    formats: list[dict[str, Any]]
    default_format: str
    features: dict[str, bool]
    session_secret: str
    session_https_only: bool
    session_max_age: int = 8 * 3600
    warnings: list[str] = field(default_factory=list)

    def ep(self, name: str) -> str:
        return self.endpoints.get(name, name)

    def format(self, format_id: str | None) -> dict[str, Any]:
        for item in self.formats:
            if item["id"] == format_id:
                return item
        return next((f for f in self.formats if f["id"] == self.default_format), self.formats[0])

    def public(self, lang: str) -> dict[str, Any]:
        """Część konfiguracji widoczna w przeglądarce (bez adresów i sekretów)."""
        return {
            "lang": lang,
            "languages": self.languages,
            "brand": self.brand,
            "authMode": self.auth_mode,
            "historyLimit": self.history_limit,
            "answerTimeoutS": self.timeout_answer,
            "defaultFormat": self.default_format,
            "formats": [
                {
                    "id": f["id"],
                    "label": _localized(f.get("label"), lang, f["id"]),
                    "description": _localized(f.get("description"), lang, ""),
                }
                for f in self.formats
            ],
            "features": self.features,
        }


def _localized(value: Any, lang: str, fallback: str) -> str:
    if isinstance(value, dict):
        return value.get(lang) or value.get("pl") or next(iter(value.values()), fallback)
    return value or fallback


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(path: str | os.PathLike | None = None) -> Settings:
    cfg_path = Path(path or os.environ.get("UI_CONFIG") or os.environ.get("UI_CONFIG_PATH") or DEFAULT_PATH)
    if not cfg_path.exists():
        cfg_path = EXAMPLE_PATH
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    warnings: list[str] = []

    sse = raw.get("api_hosts", {}).get("semantic_search_engine", {})
    host = os.environ.get("SSE_API_HOST") or sse.get("host") or "http://localhost:8271"
    prefix = os.environ.get("SSE_API_PREFIX", sse.get("prefix", "api"))
    auth = raw.get("auth", {})
    ui = raw.get("ui", {})
    timeouts = raw.get("timeouts", {})
    defaults = raw.get("defaults", {})
    formats = raw.get("formats") or []
    if not formats:
        raise ValueError("Konfiguracja musi zawierać co najmniej jeden format w sekcji 'formats'")

    secret = os.environ.get("SESSION_SECRET") or os.environ.get("UI_SECRET_KEY") or raw.get("session_secret") or ""
    if not secret:
        secret = secrets.token_urlsafe(32)
        warnings.append("Brak SESSION_SECRET – wygenerowano losowy; sesje znikną po restarcie.")

    return Settings(
        raw=raw,
        api_host=host.rstrip("/"),
        api_prefix=prefix.strip("/"),
        verify_tls=bool(sse.get("verify_tls", True)),
        endpoints=dict(sse.get("ep", {})),
        auth_mode=os.environ.get("AUTH_MODE", auth.get("mode", "local")),
        sso_button=bool(auth.get("sso_button", False)),
        default_language=ui.get("default_language", "pl"),
        languages=list(ui.get("languages", ["pl", "en"])),
        brand=ui.get("brand", "radlab.dev"),
        history_limit=int(ui.get("history_limit", 50)),
        timeout_default=float(timeouts.get("default_s", 30)),
        timeout_answer=float(timeouts.get("add_user_message_s", 150)),
        options=dict(defaults.get("options", {})),
        search_options=dict(defaults.get("search_options", {})),
        preview_pages=int(defaults.get("document_preview_pages", 3)),
        citation_instruction=raw.get("citation_instruction", ""),
        formats=formats,
        default_format=raw.get("default_format", formats[0]["id"]),
        features={k: bool(v) for k, v in raw.get("features", {}).items()},
        session_secret=secret,
        session_https_only=_env_bool("SESSION_HTTPS_ONLY", False),
        warnings=warnings,
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
