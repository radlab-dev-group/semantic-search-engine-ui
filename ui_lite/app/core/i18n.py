"""Interface texts in `app/locales/<lang>.json` files (PL, EN)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Translator:
    def __init__(self, directory: Path, languages: list[str], default: str) -> None:
        self.default = default if default in languages else languages[0]
        self.languages = languages
        self.texts: dict[str, dict[str, str]] = {}
        for lang in languages:
            path = directory / f"{lang}.json"
            self.texts[lang] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def pick(self, lang: str | None) -> str:
        return lang if lang in self.languages else self.default

    def bundle(self, lang: str) -> dict[str, str]:
        """All texts for a language; missing keys are filled in from the default language."""
        base = dict(self.texts.get(self.default, {}))
        base.update(self.texts.get(lang, {}))
        return base

    def t(self, lang: str, key: str, **values: Any) -> str:
        text = self.bundle(lang).get(key, key)
        for name, value in values.items():
            text = text.replace("{" + name + "}", str(value))
        return text
