from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routes.common import lang_of, templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def app_page(request: Request):
    if not request.session.get("token"):
        return RedirectResponse("/login", status_code=303)
    s = request.app.state.settings
    lang = lang_of(request)
    return templates.TemplateResponse(
        request,
        "app.html",
        {
            "t": request.app.state.i18n.bundle(lang),
            "lang": lang,
            "brand": s.brand,
            "user": request.session.get("user") or "",
            "config": s.public(lang),
        },
    )


@router.get("/healthz")
async def healthz():
    """Stan samego frontendu (dla orkiestracji kontenerów)."""
    return {"status": "ok"}
