"""Local login (`POST login`) and SSO via Keycloak/OAuth (`login_url`, `login` with a code, `logout`)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.api_client import ApiError
from app.routes.common import lang_of, templates

router = APIRouter()


def _start_session(
    request: Request, token: str, user: str, refresh: str | None = None
) -> None:
    lang = lang_of(request)
    request.session.clear()
    request.session.update(
        {
            "token": token,
            "user": user,
            "sid": secrets.token_urlsafe(16),
            "lang": lang,
        }
    )
    if refresh:
        request.session["refresh_token"] = refresh


def _login_page(
    request: Request, error: str = "", status: int = 200
) -> HTMLResponse:
    s = request.app.state.settings
    lang = lang_of(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "t": request.app.state.i18n.bundle(lang),
            "lang": lang,
            "languages": s.languages,
            "brand": s.brand,
            "error": error,
            "local": s.auth_mode == "local",
            "sso": s.auth_mode == "sso" or s.sso_button,
        },
        status_code=status,
    )


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, error: str = "") -> HTMLResponse:
    if request.session.get("token"):
        return RedirectResponse("/", status_code=303)
    i18n = request.app.state.i18n
    message = i18n.t(lang_of(request), f"login.error.{error}") if error else ""
    return _login_page(request, message)


@router.post("/login")
async def login_local(
    request: Request, username: str = Form(""), password: str = Form("")
):
    i18n, lang = request.app.state.i18n, lang_of(request)
    if not username.strip() or not password:
        return _login_page(request, i18n.t(lang, "login.error.empty"), 400)
    try:
        body = await request.app.state.api.call(
            "POST",
            "login",
            lang=lang,
            json={"username": username.strip(), "password": password},
        )
    except ApiError as exc:
        key = (
            "unavailable"
            if exc.kind in {"unavailable", "timeout"}
            else "credentials"
        )
        return _login_page(
            request,
            i18n.t(lang, f"login.error.{key}"),
            401 if key == "credentials" else 503,
        )
    token = (body or {}).get("token") if isinstance(body, dict) else None
    if not token:
        return _login_page(request, i18n.t(lang, "login.error.credentials"), 401)
    _start_session(request, str(token), username.strip())
    return RedirectResponse("/", status_code=303)


@router.get("/login/sso")
async def login_sso(request: Request):
    try:
        body = await request.app.state.api.call(
            "POST", "login_url", lang=lang_of(request), json={}
        )
    except ApiError:
        return RedirectResponse("/login?error=unavailable", status_code=303)
    url = (body or {}).get("login_url") if isinstance(body, dict) else None
    if not url:
        return RedirectResponse("/login?error=sso", status_code=303)
    return RedirectResponse(str(url), status_code=303)


@router.get("/login/callback")
async def login_callback(
    request: Request, code: str = "", state: str = "", session_state: str = ""
):
    """Return address from Keycloak – RadLab sets it as the SSO client redirect URI."""
    if not code or not state:
        return RedirectResponse("/login?error=sso", status_code=303)
    payload = {"code": code, "state": state}
    if session_state:
        payload["session_state"] = session_state
    try:
        body = await request.app.state.api.call(
            "POST", "login", lang=lang_of(request), json=payload
        )
    except ApiError:
        return RedirectResponse("/login?error=sso", status_code=303)
    body = body if isinstance(body, dict) else {}
    if not body.get("token"):
        return RedirectResponse("/login?error=sso", status_code=303)
    _start_session(
        request,
        str(body["token"]),
        str(body.get("username") or ""),
        body.get("refresh_token"),
    )
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    token = request.session.get("token")
    if token and request.session.get("refresh_token"):
        try:
            await request.app.state.api.call(
                "POST", "logout", token=token, lang=lang_of(request), json={}
            )
        except ApiError:
            pass
    sid = request.session.get("sid")
    if sid:
        request.app.state.store.drop(sid)
    lang = lang_of(request)
    request.session.clear()
    request.session["lang"] = lang
    return RedirectResponse("/login", status_code=303)


@router.get("/lang/{code}")
async def set_language(request: Request, code: str, next: str = "/"):
    request.session["lang"] = request.app.state.i18n.pick(code)
    return RedirectResponse(
        next if next.startswith("/") and not next.startswith("//") else "/",
        status_code=303,
    )
