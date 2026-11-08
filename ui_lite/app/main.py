"""FastAPI application: a minimalist RAG chat for employees (RadLab semantic-search-engine)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.api_client import ApiClient
from app.core.config import Settings, get_settings
from app.core.i18n import Translator
from app.core.session_store import MemoryStore
from app.routes import auth, pages, ui_api

APP_DIR = Path(__file__).resolve().parent
log = logging.getLogger("ui")


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    for warning in settings.warnings:
        log.warning(warning)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.api.close()

    app = FastAPI(
        title="RadLab RAG chat",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.api = ApiClient(settings, transport=transport)
    app.state.store = MemoryStore(ttl_s=settings.session_max_age)
    app.state.i18n = Translator(
        APP_DIR / "locales", settings.languages, settings.default_language
    )
    app.state.model_cache = {}

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="rag_ui",
        max_age=settings.session_max_age,
        same_site="lax",
        https_only=settings.session_https_only,
    )
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(ui_api.router)
    return app


app = create_app()
