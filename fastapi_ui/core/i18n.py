"""
Interface translations (Polish + English).

Texts live in ``app/locales/<code>.json`` (nested objects, addressed with
dotted keys such as ``"nav.search"``). A value can be:

* a string - ``{name}`` placeholders are filled with ``str.format``;
* an object with plural forms (``one`` / ``few`` / ``many`` / ``other``,
  the CLDR categories also used by ``Intl.PluralRules`` in the browser),
  selected by the ``n`` argument of :func:`translate_plural`.

Keys ending with ``_html`` hold trusted markup: they are returned as
``Markup`` and the placeholder values are escaped. Missing keys fall back to
the default language and then to the key itself, so a missing translation
never breaks a page.

The language of a request is taken from the ``sse_lang`` cookie (set by
``GET /lang/<code>``), then from the ``Accept-Language`` header and finally
from ``UI_DEFAULT_LANGUAGE`` (``en`` by default).
"""

import json
import os
from functools import lru_cache

from markupsafe import Markup

LANGUAGES = {"en": "English", "pl": "Polski"}
FALLBACK_LANGUAGE = "en"
DEFAULT_LANGUAGE = (
    os.environ.get("UI_DEFAULT_LANGUAGE", FALLBACK_LANGUAGE).strip().lower()
)
if DEFAULT_LANGUAGE not in LANGUAGES:
    DEFAULT_LANGUAGE = FALLBACK_LANGUAGE

LANGUAGE_COOKIE = "sse_lang"

LOCALES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "locales"
)


def _flatten(tree: dict, prefix: str = "") -> dict:
    flat = {}
    for key, value in tree.items():
        full_key = f"{prefix}{key}"
        if isinstance(value, dict) and not _is_plural(value):
            flat.update(_flatten(value, f"{full_key}."))
        else:
            flat[full_key] = value
    return flat


def _is_plural(value: dict) -> bool:
    return bool(value) and set(value) <= {"zero", "one", "two", "few", "many", "other"}


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict:
    """All texts of ``lang`` as a flat ``{dotted.key: value}`` dict."""
    path = os.path.join(LOCALES_DIR, f"{lang}.json")
    with open(path, encoding="utf-8") as handle:
        return _flatten(json.load(handle))


def normalize_language(value) -> str | None:
    """``"pl-PL"`` -> ``"pl"``; ``None`` for unsupported languages."""
    code = str(value or "").strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGUAGES else None


def language_from_header(header: str | None) -> str | None:
    """Best supported language of an ``Accept-Language`` header."""
    candidates = []
    for position, part in enumerate((header or "").split(",")):
        piece, _, params = part.strip().partition(";")
        quality = 1.0
        if params.strip().startswith("q="):
            try:
                quality = float(params.strip()[2:])
            except ValueError:
                quality = 0.0
        code = normalize_language(piece)
        if code and quality > 0:
            candidates.append((-quality, position, code))
    return min(candidates)[2] if candidates else None


def plural_category(lang: str, n) -> str:
    """CLDR plural category of an integer ``n`` (same as Intl.PluralRules)."""
    try:
        number = abs(int(n))
    except (TypeError, ValueError):
        return "other"
    if lang == "pl":
        if number == 1:
            return "one"
        if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
            return "few"
        return "many"
    return "one" if number == 1 else "other"


def _lookup(lang: str, key: str):
    for code in (lang, DEFAULT_LANGUAGE, FALLBACK_LANGUAGE):
        if code in LANGUAGES:
            value = catalog(code).get(key)
            if value is not None:
                return value
    return None


def _format(key: str, template: str, kwargs: dict):
    if key.endswith("_html"):
        return Markup(template).format(**kwargs) if kwargs else Markup(template)
    try:
        return template.format(**kwargs) if kwargs else template
    except (KeyError, IndexError, ValueError):
        return template


def translate(lang: str, key: str, **kwargs):
    value = _lookup(lang, key)
    if value is None:
        return key
    if isinstance(value, dict):
        return translate_plural(lang, key, kwargs.pop("n", 0), **kwargs)
    return _format(key, str(value), kwargs)


def translate_plural(lang: str, key: str, n, **kwargs):
    value = _lookup(lang, key)
    if value is None:
        return key
    if not isinstance(value, dict):
        return _format(key, str(value), {"n": n, **kwargs})
    category = plural_category(lang, n)
    template = value.get(category) or value.get("other") or value.get("many") or ""
    return _format(key, str(template), {"n": n, **kwargs})


class Translator:
    """Per-request translation helpers exposed to the templates."""

    def __init__(self, lang: str):
        self.lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE

    def __call__(self, key: str, **kwargs):
        return translate(self.lang, key, **kwargs)

    def plural(self, key: str, n, **kwargs):
        return translate_plural(self.lang, key, n, **kwargs)

    def section(self, prefix: str) -> dict:
        """Texts below ``prefix`` (e.g. ``"js"``) as ``{subkey: value}``.

        Used to hand the strings of the client side script over to app.js.
        """
        merged = {}
        for code in (FALLBACK_LANGUAGE, DEFAULT_LANGUAGE, self.lang):
            for key, value in catalog(code).items():
                if key.startswith(f"{prefix}."):
                    merged[key[len(prefix) + 1:]] = value
        return merged
