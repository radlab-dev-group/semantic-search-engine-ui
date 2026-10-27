"""
FastAPI + Jinja2 web interface for Semantic Search Engine.

Application routes:
    /home              -> Home page with project description
    /login, /logout    -> User authentication (Django token)
    /collections       -> Knowledge base: collections management
    /collections/manage-> Knowledge base: document and chunk management
    /collections/documents/preview -> Whole content of one document (new window)
    /documents/upload  -> Knowledge base: document upload and text indexing
    /search            -> Semantic & hybrid search, generative QA, and rating
    /search/history    -> Search history per collection

Run with:
    cd fastapi_ui && bash run.sh
or:
    cd fastapi_ui && uvicorn server:app --host 0.0.0.0 --port 8000
"""

import datetime
import json
import logging
import os
import re
import uuid
from urllib.parse import quote, urlencode

import pandas as pd
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from starlette.datastructures import FormData
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
)

from core import constants, i18n
from core.api import SemanticSearchEngineAPI
from core.markdown import render_markdown
from core.state_store import (
    LAST_QUERY_RESPONSE_ID,
    LAST_SEARCH_PARAMS,
    PENDING_GENERATIONS,
)
from core.state_store import clear_state, get_state, set_state

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("fastapi_ui")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get(
    "UI_CONFIG_PATH", os.path.join(BASE_DIR, "configs", "ui-configuration.json")
)

app = FastAPI(title="Semantic Search Engine UI (FastAPI)", docs_url="/docs")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("UI_SECRET_KEY", "change-me-in-production"),
    session_cookie="sse_ui_session",
    max_age=60 * 60 * 24 * 7,
)
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "app", "static")),
    name="static",
)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "app", "templates"))
templates.env.globals["constants"] = constants
templates.env.globals["languages"] = i18n.LANGUAGES

# Engine answers arrive as Markdown; render_markdown() escapes raw HTML, so the
# result can be marked safe (see core/markdown.py).
templates.env.filters["markdown"] = lambda text: Markup(render_markdown(text))

# Single API client shared by all routes (mirrors pages/src/constants.py)
sse_api_engine = SemanticSearchEngineAPI(config_path=CONFIG_PATH)


# --------------------------------------------------------------------------- #
# Session helpers
# --------------------------------------------------------------------------- #
def get_token(request: Request) -> str | None:
    token = request.session.get("sse_token")
    if token is None or not str(token).strip():
        return None
    return token


def get_username(request: Request) -> str | None:
    username = request.session.get("sse_login")
    if username is None or not str(username).strip():
        return None
    return username


def require_login(request: Request) -> RedirectResponse | None:
    """Return a redirect to the login page when the user is not logged in."""
    if get_token(request) is None or get_username(request) is None:
        return RedirectResponse(url="/login", status_code=303)
    return None


def clear_session_state(request: Request) -> None:
    """Drop the per-session engine state (id of the last generated answer)."""
    clear_state(request)


def get_last_response_id(request: Request):
    return get_state(request).get(LAST_QUERY_RESPONSE_ID)


# --------------------------------------------------------------------------- #
# Interface language (pl / en), see core/i18n.py
# --------------------------------------------------------------------------- #
def get_language(request: Request) -> str:
    """Cookie chosen with the language switch, then Accept-Language."""
    return (
        i18n.normalize_language(request.cookies.get(i18n.LANGUAGE_COOKIE))
        or i18n.language_from_header(request.headers.get("accept-language"))
        or i18n.DEFAULT_LANGUAGE
    )


def translator(request: Request) -> i18n.Translator:
    return i18n.Translator(get_language(request))


def safe_next_url(value: str | None) -> str:
    """Local path to return to after switching the language."""
    target = str(value or "").strip()
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


def render_page(
    request: Request, name: str, status_code: int = 200, **context
) -> HTMLResponse:
    t = translator(request)
    context.setdefault("t", t)
    context.setdefault("lang", t.lang)
    context.setdefault("js_i18n", {"lang": t.lang, "texts": t.section("js")})
    context.setdefault("username", get_username(request))
    context.setdefault("is_logged_in", get_token(request) is not None)
    return templates.TemplateResponse(
        request, name, context, status_code=status_code
    )


def render_api_error(
    request: Request, result, status_code: int = 502
) -> HTMLResponse:
    """Render error response page."""
    errors = result.get("errors", []) if isinstance(result, dict) else []
    return render_page(
        request,
        "error.html",
        status_code=status_code,
        error_result=result,
        errors=errors,
    )


# Upload limits (in MB, per single uploaded file/part)
MAX_UPLOAD_SIZE_MB = float(os.environ.get("UI_MAX_UPLOAD_SIZE_MB", "6000"))
MAX_UPLOAD_FILES = int(os.environ.get("UI_MAX_UPLOAD_FILES", "500"))


async def parsed_form(request: Request) -> FormData:
    """Form (with uploaded files) resolved before the sync endpoint runs."""
    limit = int(MAX_UPLOAD_SIZE_MB * 1024 * 1024)
    try:
        return await request.form(max_files=MAX_UPLOAD_FILES, max_part_size=limit)
    except TypeError:  # older Starlette without the size limit arguments
        return await request.form()


# --------------------------------------------------------------------------- #
# Chunking: how the texts of a collection are split (engine contract)
# --------------------------------------------------------------------------- #
MAX_TOKENS_KEY = "max_tokens_in_chunk"
OVERLAP_KEY = "number_of_overlap_tokens"
# errors[].error_code of the engine (HTTP 200, status False)
CHUNKING_TOO_LONG = "000005_DATA"  # chunk > max_model_length of the embedder
CHUNKING_MISMATCH = "000006_DATA"  # strict collection, other values requested
CHUNKING_ERROR_CODES = {CHUNKING_TOO_LONG: "too_long", CHUNKING_MISMATCH: "mismatch"}


def as_int(value) -> int | None:
    """Integer of a form field / JSON value, ``None`` when empty or invalid."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_chunking(value) -> dict | None:
    """``{max_tokens_in_chunk, number_of_overlap_tokens}`` with integers, or
    ``None`` when the chunk size is missing (the overlap defaults to 0)."""
    if not isinstance(value, dict):
        return None
    max_tokens = as_int(value.get(MAX_TOKENS_KEY))
    if max_tokens is None:
        return None
    return {MAX_TOKENS_KEY: max_tokens, OVERLAP_KEY: as_int(value.get(OVERLAP_KEY)) or 0}


def collection_chunking(metadata) -> dict:
    """Chunking declared on a collection (``metadata_json`` of GET collections).

    ``metadata_json`` is ``null`` for collections which never declared a
    chunking (the engine then uses its defaults and binds them on the first
    indexing), otherwise ``{"chunking": {...}, "strict_chunking": bool}``.
    Returns ``chunking`` (dict or None) and ``strict_chunking`` (bool or None
    when undeclared).
    """
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            metadata = None
    if not isinstance(metadata, dict):
        return {"chunking": None, "strict_chunking": None}
    strict = metadata.get("strict_chunking")
    if isinstance(strict, str):
        strict = strict.strip().lower() in ("true", "1", "yes")
    return {
        "chunking": parse_chunking(metadata.get("chunking")),
        "strict_chunking": bool(strict) if strict is not None else None,
    }


def fetch_chunking_defaults(token: str) -> dict | None:
    """``chunking_defaults`` of GET filter_options: what the engine uses for
    a collection without a declared chunking. ``None`` when unavailable."""
    try:
        result = sse_api_engine.filter_options(token=token)
    except Exception as error:  # the page is still usable without them
        logger.warning("Cannot fetch chunking defaults: %s", error)
        return None
    if not isinstance(result, dict) or not result.get("status"):
        return None
    body = result.get("body") or {}
    return parse_chunking(body.get("chunking_defaults")) if isinstance(body, dict) else None


def chunking_error(result) -> dict | None:
    """First chunking error of an engine answer.

    Returns ``{"code": "too_long" | "mismatch", "message": str}`` - the message
    comes from the engine (already in the language asked for with ``lang``) -
    or ``None`` when the answer carries no such error.
    """
    if not isinstance(result, dict):
        return None
    for error in result.get("errors") or []:
        if not isinstance(error, dict):
            continue
        code = CHUNKING_ERROR_CODES.get(str(error.get("error_code") or "").strip())
        if code:
            return {"code": code, "message": str(error.get("message") or "").strip()}
    return None


def parse_indexing_options(form: FormData) -> dict:
    """indexing_options of the engine, the same for uploaded files and texts.

    The chunk keys are optional: without them the engine splits the texts as
    the collection declares (or with its defaults). ``chunking_mode`` of the
    form says whether the user keeps the settings of the collection
    (``collection``) or overrides them (``custom``), in which case both keys
    are sent. Forms without the mode send the keys they carry.
    """
    options = {
        "clear_text": form.get("clear_text") is not None,
        "use_text_denoiser": form.get("use_text_denoiser") is not None,
        "check_text_lang": form.get("check_text_lang") is not None,
        "prepare_proper_pages": form.get("prepare_proper_pages") is not None,
        "merge_document_pages": form.get("merge_document_pages") is not None,
        # The file of an uploaded document disappears from the disk of the
        # engine once its embeddings are stored (a document which fails
        # indexing keeps its file).  The form of the pasted texts has no such
        # switch: those texts were never files here.
        "delete_files_after_indexing": form.get("delete_files_after_indexing")
        is not None,
    }
    if form.get("chunking_mode") == "collection":
        return options
    max_tokens = as_int(form.get(MAX_TOKENS_KEY))
    overlap = as_int(form.get(OVERLAP_KEY))
    if max_tokens is not None and overlap is not None:
        options[MAX_TOKENS_KEY] = max_tokens
        options[OVERLAP_KEY] = overlap
    return options


# --------------------------------------------------------------------------- #
# Data preparation
# --------------------------------------------------------------------------- #
def _clean_collection_part(name: str) -> str:
    return (
        name.replace(" ", "_")
        .replace("'", "")
        .replace('"', "")
        .replace(".", "_")
        .replace("\t", "_")
    )


def proper_collection_name(orig_col_name: str, username_str: str) -> str:
    prefix = _clean_collection_part(username_str)
    name = _clean_collection_part(orig_col_name)
    return f"{prefix}_{name}"


def format_count(value) -> str:
    """Count with a space as the thousands separator ("12 000")."""
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def format_generation_time(seconds) -> str | None:
    if seconds is None:
        return None
    try:
        return str(datetime.timedelta(seconds=float(seconds)))
    except (TypeError, ValueError):
        return str(seconds)


def fetch_collections(token: str) -> dict:
    return sse_api_engine.list_user_collections(token=token)


def format_created_on(value) -> str:
    """Engine timestamps are ISO strings; the date is all the list shows.

    The engine emits ``...Z`` (UTC) suffixes, which ``fromisoformat`` accepts
    only from Python 3.11 on, so the designator is normalised first.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    iso = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%Y-%m-%d")
    except ValueError:
        return text


def format_created_on_time(value) -> str:
    """Engine timestamp as ``YYYY-MM-DD HH:MM``, or an empty string.

    The history of the searches happens during a day, so the time of day is
    what tells two searches apart; the same ``Z`` suffix of the engine is
    normalised as in :func:`format_created_on`.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    iso = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text


def collection_row(entry) -> dict | None:
    """One entry of ``collections`` as a table row.

    Same fields as ``sse_lib.models.Collection``, i.e. what
    ``SSEClient.list_collections()`` of ../semantic-search-engine/sse_lib
    returns; entries without a name are skipped.
    """
    if not isinstance(entry, dict):
        entry = {"name": entry}
    name = str(entry.get("name") or "").strip()
    if not name:
        return None
    return {
        "id": entry.get("id"),
        "name": name,
        "display_name": str(entry.get("display_name") or "").strip() or name,
        "description": str(entry.get("description") or "").strip(),
        "created_on": format_created_on(entry.get("created_on")),
        # counters of GET collections: None = an engine which does not send
        # them yet (before 0.1.5), the card then shows nothing instead of a 0
        "document_count": as_int(entry.get("document_count")),
        "active_document_count": as_int(entry.get("active_document_count")),
        # chunking: None = no declaration yet (metadata_json is null)
        **collection_chunking(entry.get("metadata_json")),
    }


def fetch_collection_rows(token: str) -> dict:
    """Collections of the user (and of its organisation) prepared for display.

    Wraps ``GET api/collections`` - the call behind
    ``sse_lib.SSEClient.list_collections()`` - and keeps the order returned by
    the engine (own collections first, then the organisational ones).
    """
    result = fetch_collections(token)
    if "status" in result and not result["status"]:
        return {"error": result}
    body = result.get("body") or {}
    entries = body.get("collections") if isinstance(body, dict) else []
    rows = [row for row in (collection_row(entry) for entry in entries or []) if row]
    return {"collections": rows}


def collection_indexing(token: str, collection_name: str) -> dict | None:
    """The running job of a collection as the bar of its card.

    ``None`` when the engine has no ``api/indexing_status``, the call fails,
    the collection has never been indexed or its newest job has finished -
    the card then shows no bar.  A running job answers with its ``job_id``
    and the numbers ``app.js`` watches (``percent`` and ``finished``) so it
    can reload the page only when something changed.
    """
    status = fetch_indexing_status(token, collection_name)
    if not status:
        return None
    job = status.get("job")
    if not isinstance(job, dict) or job.get("finished"):
        return None
    return {
        "job_id": as_int(job.get("id")),
        "status": str(job.get("status") or "indexing"),
        "percent": as_int(job.get("percent")) or 0,
        "finished": bool(job.get("finished")),
    }


def fetch_collection_filters(token: str, collection_name: str) -> dict:
    """Categories and documents of a single collection (sidebar filters)."""
    categories: list = []
    documents: list = []

    if not collection_name:
        return {"categories": categories, "documents": documents}

    categories_result = sse_api_engine.list_categories_from_collection(
        token=token, collection_name=collection_name
    )
    if categories_result.get("status"):
        raw = categories_result.get("body", {}).get("categories", []) or []
        categories = sorted(c for c in raw if c is not None and len(c))

    documents_result = sse_api_engine.list_documents_from_collection(
        token=token, collection_name=collection_name
    )
    if documents_result.get("status"):
        documents = sorted(
            doc["name"]
            for doc in documents_result["body"]["documents"]
            if len(doc["name"]) and doc.get("use_in_search", True) is not False
        )

    return {"categories": categories, "documents": documents}


def document_row(entry) -> dict | None:
    """One document of the collection with its ``use_in_search`` flag.

    An engine which does not report the flag lists only the documents used in
    the search, so a missing flag means "enabled".
    """
    if not isinstance(entry, dict):
        entry = {"name": entry}
    name = str(entry.get("name") or "").strip()
    if not name:
        return None
    flag = entry.get("use_in_search", True)
    if isinstance(flag, str):
        flag = flag.strip().lower() not in ("false", "0", "no", "off", "")
    return {**entry, "name": name, "use_in_search": bool(flag)}


def fetch_indexing_status(
    token: str, collection_name: str = "", job_id: int | None = None
) -> dict | None:
    """Progress of the indexing of a collection (its newest job) or of one job.

    Wraps ``GET api/indexing_status``. ``None`` when the question cannot be
    answered - an engine without the endpoint, a failing call, a collection
    without indexing - so a page is rendered without the progress panel.
    """
    if not collection_name and job_id is None:
        return None
    try:
        response = sse_api_engine.indexing_status(
            token=token, collection_name=collection_name, job_id=job_id
        )
    except Exception as error:  # the panel must not break the page
        logger.warning("Cannot fetch the indexing status: %s", error)
        return None
    if not isinstance(response, dict) or response.get("status") is False:
        return None
    body = response.get("body")
    if not isinstance(body, dict):
        return None
    return {
        "job": body.get("job") if isinstance(body.get("job"), dict) else None,
        "documents": [
            document
            for document in body.get("documents") or []
            if isinstance(document, dict)
        ],
        "pending_documents": int(body.get("pending_documents") or 0),
    }


def fetch_manage_collection_context(token: str, collection_name: str = "") -> dict:
    """All data required to render the collection management page."""
    data = fetch_collection_rows(token)
    if "error" in data:
        return {"error": data["error"]}
    collections = data["collections"]
    if not collections:
        return {
            "collections": [],
            "selected_collection": "",
            "active_coll_info": None,
            "documents": [],
            "categories": [],
            "indexing": None,
        }

    valid_names = [c["name"] for c in collections]
    if not collection_name or collection_name not in valid_names:
        selected_collection = collections[0]["name"]
    else:
        selected_collection = collection_name

    active_coll_info = next(
        (c for c in collections if c["name"] == selected_collection), None
    )

    # The progress is read before the documents: the badges of the rows and the
    # panel of the page then describe the same moment of the indexing.
    indexing = fetch_indexing_status(token, selected_collection)

    documents: list = []
    docs_result = sse_api_engine.list_documents_from_collection(
        token=token, collection_name=selected_collection, with_disabled=True
    )
    if docs_result.get("status"):
        raw_docs = docs_result.get("body", {}).get("documents", []) or []
        documents = [doc for doc in (document_row(d) for d in raw_docs) if doc]

    categories: list = []
    categories_result = sse_api_engine.list_categories_from_collection(
        token=token, collection_name=selected_collection
    )
    if categories_result.get("status"):
        raw_cats = categories_result.get("body", {}).get("categories", []) or []
        categories = sorted(c for c in raw_cats if c is not None and len(c))

    return {
        "collections": collections,
        "selected_collection": selected_collection,
        "active_coll_info": active_coll_info,
        "documents": documents,
        "disabled_count": sum(1 for doc in documents if not doc["use_in_search"]),
        "categories": categories,
        # ``None`` when the engine has no api/indexing_status
        "indexing": indexing,
    }


# --------------------------------------------------------------------------- #
# Preview of a whole document: the engine may return it as one text or as the
# pieces it is built of (its pages, or the text chunks of the index).
# --------------------------------------------------------------------------- #
DOCUMENT_TEXT_KEYS = ("content", "text", "text_str", "page_content", "document_content")
DOCUMENT_PIECE_LIST_KEYS = ("pages", "texts", "chunks")
DOCUMENT_PIECE_NUMBER_KEYS = (
    "page",
    "page_number",
    "text_number",
    "chunk_number",
    "id",
)


# The whitespace an indexed document brings with it: a PDF sets the words of a
# line apart with a run of spaces and leaves whole empty lines between the
# blocks of its page.  A preview window reads a document, it does not
# reproduce the layout of its source, so the preview makes one space of a run
# of them, shows at most one empty line in a row and caps an indentation no
# author meant.  The words and the line breaks stay where the engine has them,
# and the .txt download carries the text of the engine as it is.
PREVIEW_INNER_SPACE = re.compile(r"(?<=\S)[ \t]{2,}(?=\S)")
PREVIEW_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
PREVIEW_EMPTY_LINES = re.compile(r"\n{3,}")
PREVIEW_INDENT = re.compile(r"^[ \t]{9,}", re.MULTILINE)
PREVIEW_INDENT_LIMIT = " " * 8
PREVIEW_TEXT_TAIL = re.compile(r"\s+$")


def preview_text(text: str) -> str:
    """Text of a document as the preview window shows it."""
    text = PREVIEW_INNER_SPACE.sub(" ", text)
    text = PREVIEW_TRAILING_SPACE.sub("", text)
    text = PREVIEW_EMPTY_LINES.sub("\n\n", text)
    text = PREVIEW_INDENT.sub(PREVIEW_INDENT_LIMIT, text)
    return PREVIEW_TEXT_TAIL.sub("", text)


def document_piece_text(piece) -> str | None:
    """Text of one page / chunk of the engine response, ``None`` when the
    entry carries none."""
    if isinstance(piece, str):
        return piece
    if not isinstance(piece, dict):
        return None
    for key in DOCUMENT_TEXT_KEYS:
        value = piece.get(key)
        if isinstance(value, str):
            return value
    return None


def document_preview_pages(pieces) -> list:
    """Pages / chunks of the response as ``[{page, text}]`` in their own order.

    The chunks keep the number the engine gives them, so the stitched text of a
    document reads the same way as the document itself.
    """
    rows: list = []
    for position, piece in enumerate(pieces or [], start=1):
        text = document_piece_text(piece)
        if text is None:
            continue
        number = position
        if isinstance(piece, dict):
            for key in DOCUMENT_PIECE_NUMBER_KEYS:
                if piece.get(key) is not None:
                    number = piece[key]
                    break
        try:
            number = int(number)
        except (TypeError, ValueError):
            number = position
        rows.append({"page": number, "text": text})
    return rows


def document_preview_body(result) -> tuple[list, str]:
    """``(pages, whole text)`` of a ``GET api/document_content`` response.

    The engine answers with the stitched ``content`` and the very same text
    page by page (``pages[]``); the pages win, so that the window can number
    them and the text reads identically in both.  The other shapes an engine
    may answer with are still accepted: a text field of ``body``, the list of
    its pages or of its text chunks, or a text as ``body`` itself.
    """
    body = result.get("body") if isinstance(result, dict) else None
    if isinstance(body, str):
        return [], body
    if not isinstance(body, dict):
        return [], ""
    candidates = [body]
    if isinstance(body.get("document"), dict):
        candidates.append(body["document"])
    for key in DOCUMENT_PIECE_LIST_KEYS:
        for entry in candidates:
            value = entry.get(key)
            if isinstance(value, list):
                pages = document_preview_pages(value)
                if pages:
                    return pages, "\n\n".join(page["text"] for page in pages)
    for entry in candidates:
        for key in DOCUMENT_TEXT_KEYS:
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                return [], value
    return [], ""


def document_preview_window(result) -> dict:
    """Page window of a ``GET api/document_content`` answer.

    The engine reads a document in a window of pages and says what is left:
    ``total_pages`` how many pages the document has and ``truncated`` that the
    answer is only a part of it (``next_page`` says where the next part
    starts).  The caller compares the window with the pages it was able to
    show, so a complete answer never warns about a missing rest.
    """
    body = result.get("body") if isinstance(result, dict) else None
    if not isinstance(body, dict):
        return {"total_pages": 0, "partial": False}
    entry = body.get("document") if isinstance(body.get("document"), dict) else body
    total_pages = entry.get("total_pages")
    try:
        total_pages = int(total_pages)
    except (TypeError, ValueError):
        total_pages = 0
    return {
        "total_pages": total_pages if total_pages > 0 else 0,
        "partial": bool(entry.get("truncated")),
    }


def fetch_document_preview(
    token: str, collection_name: str, document_name: str
) -> dict:
    """Whole text of one document of a collection (the preview of a row).

    ``error`` is ``"engine"`` when the engine refused or has no
    ``api/document_content``, and ``"empty"`` when it answered without any text,
    so the window explains what happened instead of showing a blank page.
    """
    try:
        result = sse_api_engine.document_content(
            token=token,
            collection_name=collection_name,
            document_name=document_name,
        )
    except Exception as error:  # the preview must not break the window
        logger.warning("Cannot fetch the content of %s: %s", document_name, error)
        return {"error": "engine"}
    if not isinstance(result, dict) or not result.get("status"):
        logger.warning("The engine refused the content of %s", document_name)
        return {"error": "engine"}

    pages, text = document_preview_body(result)
    if not text.strip():
        return {
            "error": "empty",
            "pages": [],
            "text": "",
            "total_pages": 0,
            "partial": False,
        }

    body = result.get("body")
    entry = body.get("document") if isinstance(body, dict) else None
    entry = entry if isinstance(entry, dict) else (body or {})
    relative_path = entry.get("relative_path")
    window = document_preview_window(result)
    return {
        "pages": pages,
        "text": text,
        "relative_path": relative_path if isinstance(relative_path, str) else "",
        "total_pages": window["total_pages"],
        "partial": window["partial"],
    }


def preview_filename(document_name: str) -> str:
    """Name of the .txt file downloaded from the preview window."""
    stem = os.path.splitext(os.path.basename(document_name))[0]
    stem = re.sub(r"[^\w.\-]+", "_", stem, flags=re.UNICODE).strip("._")
    return f"{stem or 'document'}.txt"


def fetch_generative_models(token: str) -> list:
    generative_models_result = sse_api_engine.list_generative_models(token=token)
    if generative_models_result.get("status"):
        return list(generative_models_result["body"].keys())
    return []


def fetch_page_context(token: str, collection_name: str = "") -> dict:
    """All data required to render the search page."""
    data = fetch_collection_rows(token)
    if "error" in data:
        return {"error": data["error"]}

    # Rows with the full (display) name; the internal name is the value sent
    collections = data["collections"]
    selected = next((c for c in collections if c["name"] == collection_name), None)
    context = {
        "collections": collections,
        "selected_collection_label": selected["display_name"] if selected else "",
        "generative_models": fetch_generative_models(token),
    }
    context.update(fetch_collection_filters(token, collection_name))
    return context


def parse_min_similarity(raw) -> float:
    """Cosine similarity cutoff of the form, a number clamped to [0, 1].

    The engine falls back to its own default for anything outside that range,
    so a mistyped value is tamed here instead of being silently ignored there.
    """
    try:
        value = float(str(raw).strip()) if raw not in (None, "") else None
    except (TypeError, ValueError):
        value = None
    if value is None or value != value:  # None or NaN
        return float(constants.DEFAULT_MIN_SIMILARITY)
    return round(min(1.0, max(0.0, value)), 2)


def parse_search_form(form: FormData) -> dict:
    """Build (search_options, answer_options, run_models_options) from the HTML
    form."""
    results_count = int(form.get("results_count") or constants.DEFAULT_MAX_RESULTS)
    min_similarity = parse_min_similarity(form.get("min_similarity"))
    rerank_results = form.get("rerank_results") is not None
    hybrid_search = form.get("hybrid_search") is not None
    use_content_supervisor = form.get("use_content_supervisor") is not None
    # The RAG supervisor switch defaults to "on",
    # so an absent field (checkbox not rendered) means True.
    if "use_rag_supervisor" in form:
        use_rag_supervisor = form.get("use_rag_supervisor") is not None
    else:
        use_rag_supervisor = True
    return_with_factored_fields = form.get("return_with_factored_fields") is not None
    use_qa_extractive = form.get("use_qa_extractive") is not None
    use_gen_qa = form.get("use_qa_generative") is not None
    use_doc_names_in_response = form.get("use_doc_names_in_response") is not None
    qa_gen_model = form.get("qa_gen_model") or ""
    perc_rank_to_gen_qa = int(
        form.get("perc_rank_to_gen_qa") or constants.DEFAULT_PERC_RANK_TO_GEN_QA
    )
    translate_output = form.get("translate_output") is not None
    lang_options = (
        (form.get("lang_options") or constants.ANSWER_LANGUAGES[0])
        if translate_output
        else ""
    )
    top_k = int(float(form.get("top_k") or constants.DEFAULT_TOP_K))
    top_p = float(form.get("top_p") or constants.DEFAULT_TOP_P)
    temperature = float(form.get("temperature") or constants.DEFAULT_TEMPERATURE)
    typical_p = float(form.get("typical_p") or constants.DEFAULT_TYPICAL_P)
    repetition_penalty = float(
        form.get("repetition_penalty") or constants.DEFAULT_REPETITION_PENALTY
    )
    set_max_new_tokens = form.get("set_max_new_tokens") is not None
    max_new_tokens = (
        int(float(form.get("max_new_tokens") or constants.DEFAULT_MAX_NEW_TOKENS))
        if set_max_new_tokens
        else None
    )

    search_options = {
        "categories": form.getlist("categories"),
        "documents": form.getlist("documents"),
        "max_results": results_count,
        "min_similarity": min_similarity,
        "rerank_results": rerank_results,
        "hybrid_search": hybrid_search,
        "return_with_factored_fields": return_with_factored_fields,
    }
    run_models_options = {
        "use_qa_extractive": use_qa_extractive,
        "use_qa_generative": use_gen_qa,
    }
    answer_options = {
        "use_qa_extractive": use_qa_extractive,
        "use_qa_generative": use_gen_qa,
        "generative_model": qa_gen_model,
        "percentage_rank_mass": perc_rank_to_gen_qa,
        "answer_language": lang_options,
        "translate_answer": translate_output,
        "use_doc_names_in_response": use_doc_names_in_response,
        "top_k": top_k,
        "top_p": top_p,
        "temperature": temperature,
        "typical_p": typical_p,
        "repetition_penalty": repetition_penalty,
        "use_content_supervisor": use_content_supervisor,
        "use_rag_supervisor": use_rag_supervisor,
    }
    if max_new_tokens is not None:
        answer_options["max_new_tokens"] = max_new_tokens

    return {
        "search_options": search_options,
        "answer_options": answer_options,
        "run_models_options": run_models_options,
    }


def _frame(data, sort_by: str, index_label: str = "id") -> list:
    """Render an engine table as a list of row dicts.

    The engine returns the results as a dict keyed by document/result id;
    a flat list is accepted as well so a different response shape does not
    break the page.
    """
    if isinstance(data, str):
        data = json.loads(data)

    df = (
        pd.DataFrame.from_dict(data)
        if isinstance(data, dict)
        else pd.DataFrame(data)
    )
    if isinstance(data, dict):
        # The index of the transposed frame is the document / result name and
        # has to stay visible in the table.
        df = df.transpose()
        df.index.name = index_label
        df = df.reset_index()
    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=False)
    return df.to_dict(orient="records")


def prepare_stats_dataframe(stats) -> list:
    """Transposed dataframe sorted by score_weighted."""
    return _frame(stats, "score_weighted", index_label="document")


def prepare_detailed_results_dataframe(results) -> list:
    return _frame(results, "score", index_label="result_id")


# --------------------------------------------------------------------------- #
# Search history (engine: search_history / get_search_history)
# --------------------------------------------------------------------------- #
# The history panel lists at most that many searches (newest first)
HISTORY_LIMIT = 50


def _size(data) -> int:
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return 0
    return len(data) if isinstance(data, (dict, list)) else 0


def _history_results(entry: dict) -> tuple:
    """Stats and detailed results of a history entry (both shapes)."""
    results = entry.get("results") if isinstance(entry.get("results"), dict) else {}
    stats = entry.get("stats") or results.get("stats") or {}
    detailed = entry.get("detailed_results") or results.get("detailed_results") or {}
    return stats, detailed


def _history_answers(entry: dict) -> list:
    return [answer for answer in entry.get("answers") or [] if isinstance(answer, dict)]


def _history_generated_answer(entry: dict) -> dict | None:
    """The newest generated answer of a history entry."""
    for answer in reversed(_history_answers(entry)):
        if answer.get("is_generative", True) and answer.get("generated_answer"):
            return answer
    if entry.get("generated_answer"):
        return {"generated_answer": entry["generated_answer"]}
    return None


def history_row(entry) -> dict | None:
    """One search of the history panel."""
    if not isinstance(entry, dict) or entry.get("query_response_id") is None:
        return None
    stats, detailed = _history_results(entry)
    answer = _history_generated_answer(entry)
    rated = next(
        (
            item
            for item in reversed(_history_answers(entry))
            if item.get("rate_value") is not None
        ),
        None,
    )
    return {
        "id": entry["query_response_id"],
        "query": str(entry.get("query") or entry.get("query_str") or "").strip(),
        # when the search was made; an engine which does not know the field
        # yet leaves it empty and the panel shows no date
        "created_on": format_created_on_time(entry.get("created_on")),
        "collection_name": entry.get("collection_name"),
        "documents": _size(stats),
        "snippets": _size(detailed),
        "answered": answer is not None,
        "rate_value": rated.get("rate_value") if rated else None,
        "rate_value_max": (
            rated.get("rate_value_max") if rated else None
        )
        or constants.MAX_VAL_RATING_GENERATIVE_ANSWER,
    }


def fetch_search_history(token: str, collection_name: str) -> list | None:
    """Searches of the user in the collection; ``None`` when unavailable."""
    if not collection_name:
        return []
    try:
        response = sse_api_engine.search_history(
            token=token, collection_name=collection_name
        )
    except Exception:  # noqa: BLE001 - the history must not break the page
        logger.exception("Cannot fetch the search history")
        return None
    if not isinstance(response, dict) or response.get("status") is False:
        return None
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    rows = [row for row in map(history_row, body.get("history") or []) if row]
    rows = [
        row for row in rows if row["collection_name"] in (None, "", collection_name)
    ]
    return rows[:HISTORY_LIMIT]


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def index(request: Request):
    if get_token(request) is None:
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/search", status_code=303)


# --- Home ------------------------------------------------------------------- #
@app.get("/home", include_in_schema=False)
def home(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect
    return render_page(request, "home.html")


# --- Login ------------------------------------------------------------------ #
@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if get_token(request) is not None and get_username(request) is not None:
        return RedirectResponse(url="/search", status_code=303)
    return render_page(request, "login.html", username="")


@app.post("/login", include_in_schema=False)
def login_submit(
    request: Request,
    form: FormData = Depends(parsed_form),
):
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""

    token = sse_api_engine.login(username=username, password=password)
    if token is None:
        return render_page(
            request,
            "login.html",
            error=translator(request)("login.invalid_credentials"),
            username=username,
        )

    request.session["sse_token"] = token
    request.session["sse_login"] = username
    clear_session_state(request)
    return RedirectResponse(url="/search", status_code=303)


@app.get("/lang/{code}", include_in_schema=False)
def switch_language(request: Request, code: str, next: str = "/"):
    """Remember the interface language and go back to the previous page."""
    response = RedirectResponse(url=safe_next_url(next), status_code=303)
    lang = i18n.normalize_language(code)
    if lang is not None:
        response.set_cookie(
            i18n.LANGUAGE_COOKIE,
            lang,
            max_age=60 * 60 * 24 * 365,
            samesite="lax",
            httponly=True,
        )
    return response


@app.get("/logout", include_in_schema=False)
def logout(request: Request):
    clear_session_state(request)
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# --- Knowledge base: collections, documents, adding content ----------------- #
# The three pages share one header with tabs and a collection switcher; the
# collection chosen on one of them is remembered for the others.
KB_COLLECTION = "kb_collection"


def kb_collection_name(request: Request, explicit: str = "") -> str:
    """Collection asked for in the request, else the last one used."""
    name = str(explicit or "").strip()
    if name:
        set_state(request, **{KB_COLLECTION: name})
        return name
    return get_state(request).get(KB_COLLECTION) or ""


def render_kb_page(
    request: Request, name: str, collection_name: str = "", **extra
) -> HTMLResponse:
    """Documents / add content tab of the selected collection."""
    token = get_token(request)
    context = fetch_manage_collection_context(
        token, kb_collection_name(request, collection_name)
    )
    if "error" in context:
        return render_api_error(request, context["error"])
    if name == "upload_documents.html":
        # The indexing forms show what the collection splits its texts with;
        # a collection without a declaration uses the defaults of the engine
        context["chunking_defaults"] = fetch_chunking_defaults(token)
    return render_page(request, name, **{**context, **extra})


# --- Collections ------------------------------------------------------------ #
def models_info_by_name(models_info: list) -> dict:
    """``models_info`` of GET embedders / rerankers keyed by the model name.

    Each entry keeps ``max_model_length`` (``None`` = no limit known),
    ``vector_size`` (embedders only) and ``device``.
    """
    info = {}
    for entry in models_info or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        info[name] = {
            "max_model_length": as_int(entry.get("max_model_length")),
            "vector_size": as_int(entry.get("vector_size")),
            "device": str(entry.get("device") or "").strip(),
        }
    return info


def render_collections_page(request: Request, **context) -> HTMLResponse:
    """List of the collections plus the form that creates a new one."""
    token = get_token(request)
    embedders = sse_api_engine.embedders(token=token, with_info=True)
    if not isinstance(embedders, dict) or "models" not in embedders:
        return render_api_error(request, embedders)
    rerankers = sse_api_engine.rerankers(token=token, with_info=True)
    if not isinstance(rerankers, dict) or "models" not in rerankers:
        return render_api_error(request, rerankers)

    data = fetch_collection_rows(token)
    if "error" in data:
        return render_api_error(request, data["error"])

    # The bar of the card: one status question per collection, so a running
    # job is visible from the list (the details stay on the documents page)
    for row in data["collections"]:
        row["indexing"] = collection_indexing(token, row["name"])

    remembered = kb_collection_name(request)
    names = [row["name"] for row in data["collections"]]
    return render_page(
        request,
        "collections.html",
        embedders=embedders["models"],
        embedder_info=models_info_by_name(embedders["models_info"]),
        rerankers=rerankers["models"],
        reranker_info=models_info_by_name(rerankers["models_info"]),
        chunking_defaults=fetch_chunking_defaults(token),
        collections=data["collections"],
        selected_collection=remembered if remembered in names else "",
        **context,
    )


@app.get("/collections", include_in_schema=False)
def collections_page(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect
    return render_collections_page(request)


@app.get("/collections/new", include_in_schema=False)
def new_collection_page(request: Request):
    """Old address of the form, which now lives on the Collections page."""
    return RedirectResponse(url="/collections#new-collection", status_code=303)


@app.post("/collections/new", include_in_schema=False)
def new_collection_submit(request: Request, form: FormData = Depends(parsed_form)):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    username = get_username(request)
    t = translator(request)

    collection_params = {
        "collection_name": proper_collection_name(
            form.get("collection_name", ""), username or ""
        ),
        "collection_display_name": form.get("collection_display_name", ""),
        "embedder_index_type": form.get("embedder_index_type", "IVF_FLAT"),
        "collection_description": form.get("collection_description", "")
        or f"Opis kolekcji {form.get('collection_display_name', '')}",
        "model_reranker": form.get("re_ranker_model", ""),
        "model_embedder": form.get("embedder_model", ""),
        "strict_chunking": form.get("strict_chunking") is not None,
    }

    # The form is re-rendered with what was typed when the chunking is refused
    form_values = {
        key: form.get(key, "")
        for key in (
            "collection_name",
            "collection_display_name",
            "collection_description",
            "embedder_index_type",
            "embedder_model",
            "re_ranker_model",
            MAX_TOKENS_KEY,
            OVERLAP_KEY,
        )
    }
    form_values["strict_chunking"] = collection_params["strict_chunking"]

    # "chunking" goes to the engine only when the user edited the prefilled
    # defaults (app.js flags it; the values rendered with the form are the
    # fallback), otherwise the collection follows the defaults of the engine
    submitted = parse_chunking(
        {MAX_TOKENS_KEY: form.get(MAX_TOKENS_KEY), OVERLAP_KEY: form.get(OVERLAP_KEY)}
    )
    rendered = parse_chunking(
        {
            MAX_TOKENS_KEY: form.get("chunking_default_max"),
            OVERLAP_KEY: form.get("chunking_default_overlap"),
        }
    )
    edited = submitted is not None and (
        form.get("chunking_edited") == "1" or submitted != rendered
    )
    if edited:
        if not 0 <= submitted[OVERLAP_KEY] < submitted[MAX_TOKENS_KEY]:
            return render_collections_page(
                request,
                error=t("collections.chunking_overlap_error"),
                chunking_error={"code": "overlap"},
                form_values=form_values,
            )
        collection_params["chunking"] = submitted

    result = sse_api_engine.new_collection(
        token=token, collection_params=collection_params, lang=t.lang
    )
    if not result.get("status"):
        problem = chunking_error(result)
        if problem is not None:
            return render_collections_page(
                request,
                error=problem["message"] or t("collections.chunking_too_long"),
                chunking_error=problem,
                form_values=form_values,
            )
        return render_api_error(request, result)

    # The engine answers with the chunking the collection was created with
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    created = dict(collection_params)
    created["chunking"] = parse_chunking(body.get("chunking")) or collection_params.get(
        "chunking"
    )
    if "strict_chunking" in body:
        created["strict_chunking"] = bool(body.get("strict_chunking"))

    return render_collections_page(
        request, success=t("collections.created"), created=created
    )


@app.post("/collections/delete", include_in_schema=False)
def delete_collection_submit(
    request: Request, form: FormData = Depends(parsed_form)
):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    collection_name = (form.get("collection_name") or "").strip()
    if not collection_name:
        return RedirectResponse(url="/collections", status_code=303)

    result = sse_api_engine.delete_collection(
        token=token, collection_name=collection_name
    )
    if not result.get("status"):
        return render_api_error(request, result)

    if get_state(request).get(KB_COLLECTION) == collection_name:
        set_state(request, **{KB_COLLECTION: None})

    t = translator(request)
    return render_collections_page(
        request,
        deleted={
            "title": t("collections.deleted_success", name=collection_name),
            "note": t("collections.deleted_note"),
        },
    )


# --- Manage Collection ---------------------------------------------------- #
@app.get("/collections/manage", include_in_schema=False)
def manage_collection_page(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    return render_kb_page(
        request,
        "manage_collection.html",
        request.query_params.get("collection_name", ""),
    )


@app.get("/collections/documents/preview", include_in_schema=False)
def document_preview_page(request: Request):
    """The whole text of one document, opened in a new window from a row of the
    documents tab; ``?download=1`` answers with the text as a .txt file.

    The content always comes from the engine (``GET api/document_content``), so
    the preview shows the document as it was indexed, not the upload form.
    """
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    collection_name = request.query_params.get("collection_name", "").strip()
    document_name = request.query_params.get("document_name", "").strip()
    if not collection_name or not document_name:
        return RedirectResponse(url="/collections/manage", status_code=303)

    preview = fetch_document_preview(token, collection_name, document_name)
    text = preview.get("text") or ""

    if request.query_params.get("download") == "1":
        filename = preview_filename(document_name)
        return PlainTextResponse(
            text,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
            },
        )

    # the window reads the document, the download above hands out the text of
    # the engine as it is
    shown = preview_text(text)
    limit = constants.DOCUMENT_PREVIEW_MAX_CHARS
    truncated = len(shown) > limit
    # the pages are only rendered for a document shown in full
    pages = (
        []
        if truncated
        else [
            {"page": page["page"], "text": preview_text(page["text"])}
            for page in preview.get("pages") or []
        ]
    )
    total_pages = preview.get("total_pages") or 0
    return render_page(
        request,
        "document_preview.html",
        collection_name=collection_name,
        document_name=document_name,
        relative_path=preview.get("relative_path", ""),
        pages=pages,
        # the engine served a window of pages of a longer document
        partial_window=bool(preview.get("partial"))
        and bool(pages)
        and total_pages > len(pages),
        total_pages=total_pages,
        pages_count=total_pages or len(pages),
        content=shown[:limit],
        characters=len(shown),
        characters_text=format_count(len(shown)),
        truncated=truncated,
        limit_text=format_count(limit),
        error=preview.get("error"),
        manage_url=f"/collections/manage?collection_name={quote(collection_name)}",
    )


@app.post("/collections/manage/add-text", include_in_schema=False)
def manage_add_text_submit(
    request: Request, form: FormData = Depends(parsed_form)
):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    t = translator(request)
    collection_name = (form.get("collection_name") or "").strip()
    filepath = (form.get("filepath") or "").strip() or "document.txt"
    category = (form.get("category") or "").strip()
    page_content = form.get("page_content") or ""

    indexing_options = parse_indexing_options(form)

    # Shape of one texts[] element expected by the engine
    # (sse_lib.options.text_document)
    texts = [
        {
            "filepath": filepath,
            "relative_filepath": filepath,
            "category": category,
            "pages": [{"page_content": page_content}],
        }
    ]

    result = sse_api_engine.add_and_index_texts(
        token=token,
        collection_name=collection_name,
        texts=texts,
        indexing_options=indexing_options,
        lang=t.lang,
    )
    if not result.get("status"):
        problem = chunking_error(result)
        if problem is not None:
            # Back to the text form with the typed text and the refused
            # chunking marked (see indexing_options_feedback)
            return render_kb_page(
                request,
                "upload_documents.html",
                collection_name,
                add_method="text",
                error=problem["message"] or t("upload.chunking_refused"),
                chunking_error=indexing_options_feedback(
                    problem, "text", indexing_options
                ),
                text_draft={
                    "filepath": filepath,
                    "category": category,
                    "page_content": page_content,
                },
            )
        return render_api_error(request, result)

    body = result.get("body") or {}
    indexed_chunks = body.get("indexed_chunks", 1)
    # "async": true - the engine only queued the text, a worker indexes it
    queued = bool(body.get("async"))

    return render_kb_page(
        request,
        "upload_documents.html",
        collection_name,
        add_method="text",
        success=(
            t("manage.add_text_queued")
            if queued
            else t("manage.add_text_success", chunks=indexed_chunks)
        ),
        # The panel of the job just submitted is shown also when it has already
        # finished (indexing in the request ends before this line is reached)
        indexing_show=True,
    )


@app.post("/collections/manage/delete-documents", include_in_schema=False)
def manage_delete_documents_submit(
    request: Request, form: FormData = Depends(parsed_form)
):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    t = translator(request)
    collection_name = (form.get("collection_name") or "").strip()

    single_doc = (form.get("document_name") or "").strip()
    selected_docs = [d.strip() for d in form.getlist("documents[]") if d.strip()]

    doc_names = [single_doc] if single_doc else selected_docs
    if not doc_names:
        return RedirectResponse(
            url=f"/collections/manage?collection_name={collection_name}",
            status_code=303,
        )

    result = sse_api_engine.delete_documents(
        token=token,
        collection_name=collection_name,
        document_names=doc_names,
    )
    if not result.get("status"):
        return render_api_error(request, result)

    body = result.get("body") or {}
    deleted = body.get("deleted") or {}
    docs_count = deleted.get("documents", len(doc_names))
    texts_count = deleted.get("texts", 0)
    vectors_count = body.get("deleted_vectors", 0)

    return render_kb_page(
        request,
        "manage_collection.html",
        collection_name,
        deleted={
            "title": t.plural("manage.deleted_docs", docs_count),
            "items": doc_names,
            "stats": [
                t.plural("manage.deleted_chunks", texts_count),
                t.plural("manage.deleted_vectors", vectors_count),
            ],
        },
    )


TRUE_VALUES = ("1", "true", "on", "yes")


@app.post("/collections/manage/visibility", include_in_schema=False)
def manage_visibility_submit(
    request: Request, form: FormData = Depends(parsed_form)
):
    """Enable / disable documents in the search (switch of a document row or
    the bulk buttons). app.js asks for JSON and updates the row in place."""
    wants_json = "application/json" in request.headers.get("accept", "")
    redirect = require_login(request)
    if redirect is not None:
        if wants_json:
            return JSONResponse({"status": False, "login": True}, status_code=401)
        return redirect

    token = get_token(request)
    t = translator(request)
    collection_name = (form.get("collection_name") or "").strip()
    flag = form.get("use_in_search")
    if flag is None:
        flag = request.query_params.get("use_in_search", "")
    use_in_search = str(flag).strip().lower() in TRUE_VALUES

    single_doc = (form.get("toggle_document") or "").strip()
    selected_docs = [d.strip() for d in form.getlist("documents[]") if d.strip()]
    doc_names = [single_doc] if single_doc else selected_docs
    if not collection_name or not doc_names:
        if wants_json:
            return JSONResponse(
                {"status": False, "error": t("manage.visibility_error")},
                status_code=400,
            )
        return RedirectResponse(
            url=f"/collections/manage?collection_name={collection_name}",
            status_code=303,
        )

    result = sse_api_engine.set_documents_use_in_search(
        token=token,
        collection_name=collection_name,
        document_names=doc_names,
        use_in_search=use_in_search,
    )
    ok = isinstance(result, dict) and bool(result.get("status"))
    if not ok:
        if wants_json:
            return JSONResponse(
                {
                    "status": False,
                    "error": t("manage.visibility_error"),
                    "errors": result.get("errors", [])
                    if isinstance(result, dict)
                    else [],
                },
                status_code=502,
            )
        return render_api_error(request, result)

    body = result.get("body") or {}
    not_found = [str(name) for name in body.get("not_found") or []]
    changed = [name for name in doc_names if name not in not_found]
    updated = body.get("updated_documents", len(changed))
    message = t.plural(
        "manage.visibility_enabled" if use_in_search else "manage.visibility_disabled",
        updated,
    )

    if wants_json:
        return JSONResponse(
            {
                "status": True,
                "use_in_search": use_in_search,
                "documents": changed,
                "not_found": not_found,
                "message": message,
            }
        )
    return render_kb_page(
        request,
        "manage_collection.html",
        collection_name,
        success=message,
    )


@app.post("/collections/manage/delete-texts", include_in_schema=False)
def manage_delete_texts_submit(
    request: Request, form: FormData = Depends(parsed_form)
):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    t = translator(request)
    collection_name = (form.get("collection_name") or "").strip()
    chunk_ids_str = form.get("chunk_ids") or ""

    chunk_ids = []
    for part in re.split(r"[,\s]+", chunk_ids_str.strip()):
        if part.isdigit():
            chunk_ids.append(int(part))

    if not chunk_ids:
        return RedirectResponse(
            url=f"/collections/manage?collection_name={collection_name}",
            status_code=303,
        )

    result = sse_api_engine.delete_texts(
        token=token,
        collection_name=collection_name,
        chunk_ids=chunk_ids,
    )
    if not result.get("status"):
        return render_api_error(request, result)

    body = result.get("body") or {}
    deleted = body.get("deleted") or {}
    texts_count = deleted.get("texts", len(chunk_ids))
    vectors_count = body.get("deleted_vectors", 0)
    not_found = {str(chunk_id) for chunk_id in body.get("not_found") or []}

    return render_kb_page(
        request,
        "manage_collection.html",
        collection_name,
        deleted={
            "title": t.plural("manage.deleted_texts", texts_count),
            "items": [
                f"#{chunk_id}" for chunk_id in chunk_ids
                if str(chunk_id) not in not_found
            ],
            "stats": [t.plural("manage.deleted_vectors", vectors_count)],
            "note": t(
                "manage.not_found",
                ids=", ".join(f"#{chunk_id}" for chunk_id in sorted(not_found)),
            )
            if not_found
            else "",
        },
    )


# --- Upload documents ------------------------------------------------------- #
def indexing_options_feedback(problem: dict, form_name: str, options: dict) -> dict:
    """Context of ``partials/indexing_options.html`` after a refused indexing.

    ``form_name`` (``files`` / ``text``) says which of the two forms was sent;
    ``requested`` keeps the chunking the user asked for, so that a too long
    chunk can be shown (``too_long``). After a ``mismatch`` the form goes back
    to the settings of the collection, the only ones a strict collection
    accepts.
    """
    return {**problem, "form": form_name, "requested": parse_chunking(options)}


@app.get("/documents/upload", include_in_schema=False)
def upload_documents_page(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    return render_kb_page(
        request,
        "upload_documents.html",
        request.query_params.get("collection_name", ""),
    )


@app.post("/documents/upload", include_in_schema=False)
def upload_documents_submit(request: Request, form: FormData = Depends(parsed_form)):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    t = translator(request)
    collection_name = form.get("collection_name", "")
    uploaded_files = form.getlist("files[]")

    def page(**kwargs):
        return render_kb_page(
            request, "upload_documents.html", collection_name, **kwargs
        )

    if not len(uploaded_files):
        return page(error=t("upload.error_no_files"))

    indexing_options = parse_indexing_options(form)

    upload_response = sse_api_engine.upload_files(
        token=token,
        files_to_upload=uploaded_files,
        collection_name=collection_name,
        indexing_options=indexing_options,
        lang=t.lang,
    )
    if upload_response is None or upload_response.get("status") is False:
        problem = chunking_error(upload_response)
        if problem is not None:
            return page(
                add_method="files",
                error=problem["message"] or t("upload.chunking_refused"),
                chunking_error=indexing_options_feedback(
                    problem, "files", indexing_options
                ),
            )
        return page(error=t("upload.error_upload"))

    body = (
        upload_response.get("body")
        if isinstance(upload_response.get("body"), dict)
        else {}
    )
    return page(
        # "async": true - the files are stored, a worker indexes them now
        success=t("upload.queued") if body.get("async") else t("upload.success"),
        uploaded={
            "collection_name": collection_name,
            "files": len(uploaded_files),
            # None = the texts were split as the collection declares
            "chunking": parse_chunking(indexing_options),
        },
        # see manage_add_text_submit: the panel of the submitted job is shown
        indexing_show=True,
    )


# --- Semantic search engine ------------------------------------------------- #
@app.get("/search", include_in_schema=False)
def search_page(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    params = get_search_params(request)
    if request.query_params.get("clear"):
        # "Clear" empties the question and the instruction, other options stay
        params.values.pop("prompt", None)
        set_state(request, **{LAST_SEARCH_PARAMS: params.values or None})
    collection_name = request.query_params.get("collection_name") or params.value(
        "collection_name", ""
    )
    token = get_token(request)
    data = fetch_page_context(token, collection_name)
    if "error" in data:
        return render_api_error(request, data["error"])
    t = translator(request)
    delete_status = request.query_params.get("history_delete")
    return render_page(
        request,
        "search.html",
        selected_collection=collection_name,
        prompt=params.value("prompt", ""),
        search_params=params.for_collection(collection_name),
        history=fetch_search_history(token, collection_name),
        success=t("history.deleted") if delete_status == "success" else None,
        error=t("history.delete_failed") if delete_status == "error" else None,
        **data,
    )


@app.get("/search/params/reset", include_in_schema=False)
def search_params_reset(request: Request):
    """Forget the remembered sidebar options (back to the defaults).

    ``params_reset=1`` tells the browser to drop its own copy of the sidebar
    (app.js remembers the fields and the folded groups in local storage).
    """
    redirect = require_login(request)
    if redirect is not None:
        return redirect
    set_state(request, **{LAST_SEARCH_PARAMS: None})
    collection_name = request.query_params.get("collection_name", "")
    query = {"collection_name": collection_name} if collection_name else {}
    query["params_reset"] = "1"
    return RedirectResponse(url="/search?" + urlencode(query), status_code=303)


class SearchParams:
    """Options of the last search, used to fill the parameters sidebar again.

    ``values`` maps a form field to its submitted values. Empty means that
    nothing was submitted yet and the template defaults apply.
    """

    # Fields filled per collection (their options depend on it)
    COLLECTION_FIELDS = ("categories", "documents")

    def __init__(self, values: dict[str, list[str]] | None = None) -> None:
        self.values = values or {}

    @classmethod
    def from_form(cls, form: FormData) -> "SearchParams":
        values: dict[str, list[str]] = {}
        for key in form.keys():
            if key == "question":
                continue
            texts = [value for value in form.getlist(key) if isinstance(value, str)]
            if texts:
                values[key] = texts
        return cls(values)

    def __bool__(self) -> bool:
        return bool(self.values)

    def value(self, name: str, default=""):
        texts = [text for text in self.values.get(name, []) if text != ""]
        return texts[0] if texts else default

    def checked(self, name: str, default: bool = False) -> bool:
        return name in self.values if self.values else default

    def selected(self, name: str, value) -> bool:
        return str(value) in self.values.get(name, [])

    def for_collection(self, collection_name: str) -> "SearchParams":
        """Copy without the filters when another collection is shown."""
        if self.value("collection_name", "") == collection_name:
            return self
        return SearchParams(
            {
                key: texts
                for key, texts in self.values.items()
                if key not in self.COLLECTION_FIELDS
            }
        )


def get_search_params(request: Request) -> SearchParams:
    return SearchParams(get_state(request).get(LAST_SEARCH_PARAMS))


def remember_search_params(request: Request, form: FormData) -> SearchParams:
    params = SearchParams.from_form(form)
    set_state(request, **{LAST_SEARCH_PARAMS: params.values})
    return params


@app.post("/search", include_in_schema=False)
def search_submit(request: Request, form: FormData = Depends(parsed_form)):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    t = translator(request)
    collection_name = form.get("collection_name", "")
    question = form.get("question", "")
    prompt = form.get("prompt", "")

    options = parse_search_form(form)
    search_options = options["search_options"]
    answer_options = options["answer_options"]
    run_models_options = options["run_models_options"]
    # The sidebar keeps the chosen options instead of the defaults
    search_params = remember_search_params(request, form)

    def page(**kwargs):
        data = fetch_page_context(token, collection_name)
        if "error" in data:
            return render_api_error(request, data["error"])
        return render_page(
            request,
            "search.html",
            selected_collection=collection_name,
            question=question,
            prompt=prompt,
            search_params=search_params,
            # Fetched after the search, so the new one is already listed
            history=fetch_search_history(token, collection_name),
            **{**data, **kwargs},
        )

    if not question or not len(question.strip()):
        return page(error=t("search.error_empty_question"))

    results = sse_api_engine.search_answer_with_options(
        token=token,
        collection_name=collection_name,
        question=question,
        options=search_options,
    )
    if results.get("status") is False:
        return render_api_error(request, results)

    if "body" not in results or "results" not in results["body"]:
        return page(error=t("search.error_no_results_section"))

    if not len(results["body"]["results"]):
        return page(warning=t("search.warning_no_results"))

    body = results["body"]
    stats = []
    detailed = []
    try:
        if "stats" in body["results"]:
            stats = prepare_stats_dataframe(body["results"]["stats"])
        if "detailed_results" in body["results"]:
            detailed = prepare_detailed_results_dataframe(
                body["results"]["detailed_results"]
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Cannot prepare results dataframes")
        return page(error=t("search.error_prepare", error=exc))

    qa_results = []
    if run_models_options["use_qa_extractive"]:
        # Extractive QA is handled on the engine side
        pass

    # The generative answer is not awaited here: the results are shown right
    # away and the page fetches the answer from /search/generate afterwards.
    generation_id = None
    set_state(request, **{LAST_QUERY_RESPONSE_ID: None})
    if run_models_options["use_qa_generative"]:
        generation_id = add_pending_generation(
            request,
            {
                "query_response_id": body["query_response_id"],
                "prompt": prompt,
                "answer_options": answer_options,
            },
        )

    return page(
        stats=stats,
        detailed=detailed,
        qa_results=qa_results,
        generation_id=generation_id,
        history_current=body.get("query_response_id"),
    )


# Searches waiting for their generative answer (per browser session). A few
# are kept so that searches run in parallel tabs do not cancel each other.
MAX_PENDING_GENERATIONS = 5


def add_pending_generation(request: Request, job: dict) -> str:
    generation_id = uuid.uuid4().hex
    pending = dict(get_state(request).get(PENDING_GENERATIONS) or {})
    pending[generation_id] = job
    while len(pending) > MAX_PENDING_GENERATIONS:
        pending.pop(next(iter(pending)))
    set_state(request, **{PENDING_GENERATIONS: pending})
    return generation_id


def pop_pending_generation(request: Request, generation_id: str) -> dict | None:
    pending = dict(get_state(request).get(PENDING_GENERATIONS) or {})
    job = pending.pop(generation_id, None)
    set_state(request, **{PENDING_GENERATIONS: pending})
    return job


@app.post("/search/generate", include_in_schema=False)
def search_generate(request: Request, form: FormData = Depends(parsed_form)):
    """Generative answer of an already rendered search, as HTML fragments."""
    if require_login(request) is not None:
        return JSONResponse({"status": False, "error": "unauthorized"}, status_code=401)

    t = translator(request)

    def fragment(status_code: int = 200, **context) -> JSONResponse:
        context.setdefault("t", t)
        env = templates.env
        answer_html = env.get_template("partials/generative_answer.html").render(
            **context
        )
        feedback_html = ""
        if context.get("last_response_id") is not None:
            feedback_html = env.get_template("partials/feedback.html").render(
                **context
            )
        return JSONResponse(
            {
                "status": status_code == 200,
                "answer_html": answer_html,
                "feedback_html": feedback_html,
            },
            status_code=status_code,
        )

    job = pop_pending_generation(request, str(form.get("generation_id") or ""))
    if job is None:
        return fragment(status_code=409, gen_error=t("search.answer_expired"))

    result = sse_api_engine.generative_answer_from_results(
        token=get_token(request),
        query_response_id=job["query_response_id"],
        query_prompt=job["prompt"],
        query_options=job["answer_options"],
    )
    if not isinstance(result, dict) or not result.get("status"):
        errors = result.get("errors", []) if isinstance(result, dict) else []
        return fragment(
            status_code=502,
            gen_error=t("messages.error_processing"),
            errors=errors,
            error_result=result,
        )

    qa_gen_results = result.get("body") or {}
    set_state(
        request, **{LAST_QUERY_RESPONSE_ID: qa_gen_results.get("response_id")}
    )
    return fragment(
        qa_gen_results=qa_gen_results,
        qa_gen_results_time=format_generation_time(
            qa_gen_results.get("generation_time")
        ),
        last_response_id=get_last_response_id(request),
    )


@app.post("/search/rate", include_in_schema=False)
def rate_submit(request: Request, form: FormData = Depends(parsed_form)):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    last_response_id = get_last_response_id(request)
    if last_response_id is None:
        return RedirectResponse(url="/search", status_code=303)

    rate_value = int(form.get("rate_value") or 0)
    rate_comment = form.get("rate_comment") or ""

    sse_api_engine.set_rating_for_generative_answer(
        token=get_token(request),
        answer_response_id=last_response_id,
        rate_value=rate_value,
        rate_value_max=constants.MAX_VAL_RATING_GENERATIVE_ANSWER,
        rate_comment=rate_comment,
    )
    logger.info("Starring with %s for response %s", rate_value, last_response_id)
    set_state(request, **{LAST_QUERY_RESPONSE_ID: None})
    # A search opened from the history is shown again (with its new rating)
    history_id = str(form.get("history_id") or "")
    if history_id.isdigit():
        return RedirectResponse(url=f"/search/history/{history_id}", status_code=303)
    return RedirectResponse(url="/search", status_code=303)


@app.get("/search/history", include_in_schema=False)
def search_history_panel(
    request: Request, collection_name: str = "", collection_label: str = ""
):
    """History panel of a collection (HTML fragment, used when it changes)."""
    if require_login(request) is not None:
        return JSONResponse({"status": False, "error": "unauthorized"}, status_code=401)
    history = fetch_search_history(get_token(request), collection_name)
    html = templates.env.get_template("partials/search_history.html").render(
        t=translator(request),
        history=history,
        selected_collection=collection_name,
        selected_collection_label=collection_label,
        history_open=True,
    )
    return JSONResponse(
        {"status": history is not None, "count": len(history or []), "html": html}
    )


@app.post("/search/history/{query_response_id}/delete", include_in_schema=False)
async def delete_search_history(request: Request, query_response_id: int):
    """Delete one history entry and return to its collection's history."""
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    form = await request.form()
    collection_name = str(form.get("collection_name") or "")
    try:
        response = sse_api_engine.delete_search_history(
            token=get_token(request), query_response_id=query_response_id
        )
    except Exception:  # noqa: BLE001 - keep API failures within the search flow
        logger.exception("Cannot delete search history entry %s", query_response_id)
        response = None

    deleted = isinstance(response, dict) and response.get("status") is True
    if deleted:
        set_state(request, **{LAST_QUERY_RESPONSE_ID: None})
    query = {"history_delete": "success" if deleted else "error"}
    if collection_name:
        query["collection_name"] = collection_name
    return RedirectResponse(url="/search?" + urlencode(query), status_code=303)


@app.get("/search/history/{query_response_id}", include_in_schema=False)
def search_history_entry(request: Request, query_response_id: int):
    """A search from the history: its question, results and generated answer."""
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    t = translator(request)
    response = sse_api_engine.get_search_history(
        token=token, query_response_id=query_response_id
    )
    if not isinstance(response, dict) or response.get("status") is False:
        status_code = 404 if isinstance(response, dict) else 502
        return render_api_error(request, response, status_code=status_code)
    entry = response.get("body") if isinstance(response.get("body"), dict) else {}

    collection_name = entry.get("collection_name") or ""
    stats_raw, detailed_raw = _history_results(entry)
    error = None
    try:
        stats = prepare_stats_dataframe(stats_raw) if stats_raw else []
        detailed = prepare_detailed_results_dataframe(detailed_raw) if detailed_raw else []
    except Exception as exc:  # noqa: BLE001
        logger.exception("Cannot prepare results dataframes of a history entry")
        stats, detailed = [], []
        error = t("search.error_prepare", error=exc)

    answer = _history_generated_answer(entry) or {}
    qa_gen_results = None
    last_response_id = None
    if answer:
        last_response_id = answer.get("response_id") or answer.get("id")
        qa_gen_results = {
            "response_id": last_response_id,
            "answer": answer.get("generated_answer") or "",
            "answer_translated": answer.get("generated_answer_translated"),
            "generation_time": answer.get("generation_time"),
        }
    # The stored answer can be rated (again) with the feedback form
    set_state(request, **{LAST_QUERY_RESPONSE_ID: last_response_id})

    params = get_search_params(request)
    data = fetch_page_context(token, collection_name)
    if "error" in data:
        return render_api_error(request, data["error"])
    return render_page(
        request,
        "search.html",
        selected_collection=collection_name,
        question=str(entry.get("query") or entry.get("query_str") or ""),
        prompt=answer.get("query_instruction_prompt") or params.value("prompt", ""),
        search_params=params.for_collection(collection_name),
        history=fetch_search_history(token, collection_name),
        history_current=query_response_id,
        history_view=True,
        error=error,
        stats=stats,
        detailed=detailed,
        qa_results=[],
        qa_gen_results=qa_gen_results,
        qa_gen_results_time=format_generation_time(answer.get("generation_time")),
        last_response_id=last_response_id,
        rated_value=answer.get("rate_value"),
        rated_comment=answer.get("rate_comment") or "",
        **data,
    )


# --- JSON endpoints (used by the page JS) ----------------------------------- #
@app.get("/api/options", include_in_schema=False)
def api_options(request: Request, collection_name: str = ""):
    redirect_target = require_login(request)
    if redirect_target is not None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    filters = fetch_collection_filters(get_token(request), collection_name)
    return JSONResponse({"status": True, "body": filters})


@app.get("/collections/indexing-status", include_in_schema=False)
def indexing_status_json(
    request: Request, collection_name: str = "", job_id: str = ""
):
    """JSON of the indexing progress panel (app.js polls it).

    ``collection_name`` reports the newest indexing request of the collection,
    ``job_id`` one request exactly (the id the upload answered with). The
    answer is the body of ``GET api/indexing_status``: the job with its
    counters and current document, its documents with their statuses, and how
    many documents of the collection are still waiting.
    """
    redirect = require_login(request)
    if redirect is not None:
        return JSONResponse({"status": False, "login": True}, status_code=401)

    status = fetch_indexing_status(
        get_token(request),
        str(collection_name or "").strip(),
        as_int(job_id),
    )
    if status is None:
        return JSONResponse(
            {"status": False, "error": "indexing_status_unavailable"},
            status_code=502,
        )
    return JSONResponse({"status": True, **status})


@app.get("/healthz", include_in_schema=False)
def healthz():
    return JSONResponse({"status": "ok"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=500, content={"status": False, "errors": [{"msg": str(exc)}]}
        )
    return render_page(
        request,
        "error.html",
        status_code=500,
        error_result={"status": False, "errors": [{"msg": str(exc)}]},
        errors=[{"msg": str(exc), "code": "UNHANDLED"}],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("UI_HOST", "0.0.0.0"),
        port=int(os.environ.get("UI_PORT", "8000")),
    )
