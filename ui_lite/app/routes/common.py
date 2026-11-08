from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def lang_of(request: Request) -> str:
    i18n = request.app.state.i18n
    return i18n.pick(request.session.get("lang"))
