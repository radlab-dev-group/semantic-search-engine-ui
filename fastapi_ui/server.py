"""
FastAPI + Jinja2 twin of the Streamlit UI (streamlit_ui/).

Pages of the Streamlit app mapped to routes:

    streamlit_ui/Home.py                            -> /home
    streamlit_ui/pages/0_Login.py                   -> /login, /logout
    streamlit_ui/pages/1_New_Collection.py          -> /collections (list + new)
    streamlit_ui/pages/2_Upload_Documents.py        -> /documents/upload
    streamlit_ui/pages/3_Semantic_Search_Engine.py  -> /search, /search/rate

    The Streamlit conversational search page (4_Conversational_Search.py) has
    no counterpart: the Chat tab is intentionally absent from this UI.

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
from urllib.parse import urlencode

import pandas as pd
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from starlette.datastructures import FormData
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, RedirectResponse

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
# Session helpers (mirror of streamlit SessionConfig)
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
    """Mirror of streamlit ui_utils.show_error_status."""
    errors = result.get("errors", []) if isinstance(result, dict) else []
    return render_page(
        request,
        "error.html",
        status_code=status_code,
        error_result=result,
        errors=errors,
    )


# Upload limits, UI_MAX_UPLOAD_SIZE_MB is the equivalent of
# STREAMLIT_SERVER_MAX_UPLOAD_SIZE (in MB, per single uploaded file/part)
MAX_UPLOAD_SIZE_MB = float(os.environ.get("UI_MAX_UPLOAD_SIZE_MB", "6000"))
MAX_UPLOAD_FILES = int(os.environ.get("UI_MAX_UPLOAD_FILES", "500"))


async def parsed_form(request: Request) -> FormData:
    """Form (with uploaded files) resolved before the sync endpoint runs."""
    limit = int(MAX_UPLOAD_SIZE_MB * 1024 * 1024)
    try:
        return await request.form(max_files=MAX_UPLOAD_FILES, max_part_size=limit)
    except TypeError:  # older Starlette without the size limit arguments
        return await request.form()


def parse_indexing_options(form: FormData) -> dict:
    """indexing_options of the engine, the same for uploaded files and texts."""
    return {
        "clear_text": form.get("clear_text") is not None,
        "use_text_denoiser": form.get("use_text_denoiser") is not None,
        "check_text_lang": form.get("check_text_lang") is not None,
        "prepare_proper_pages": form.get("prepare_proper_pages") is not None,
        "merge_document_pages": form.get("merge_document_pages") is not None,
        "max_tokens_in_chunk": int(
            form.get("max_tokens_in_chunk") or constants.DEFAULT_MAX_TOKENS_IN_CHUNK
        ),
        "number_of_overlap_tokens": int(
            form.get("number_of_overlap_tokens") or constants.DEFAULT_OVERLAP_TOKENS
        ),
    }


# --------------------------------------------------------------------------- #
# Data preparation (mirror of streamlit ui_utils.py)
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
    """Engine timestamps are ISO strings; the date is all the list shows."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.datetime.fromisoformat(text).strftime("%Y-%m-%d")
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
            if len(doc["name"])
        )

    return {"categories": categories, "documents": documents}


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
        }

    valid_names = [c["name"] for c in collections]
    if not collection_name or collection_name not in valid_names:
        selected_collection = collections[0]["name"]
    else:
        selected_collection = collection_name

    active_coll_info = next(
        (c for c in collections if c["name"] == selected_collection), None
    )

    documents: list = []
    docs_result = sse_api_engine.list_documents_from_collection(
        token=token, collection_name=selected_collection
    )
    if docs_result.get("status"):
        documents = docs_result.get("body", {}).get("documents", []) or []

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
        "categories": categories,
    }


def fetch_generative_models(token: str) -> list:
    generative_models_result = sse_api_engine.list_generative_models(token=token)
    if generative_models_result.get("status"):
        return list(generative_models_result["body"].keys())
    return []


def fetch_page_context(token: str, collection_name: str = "") -> dict:
    """All data required to render the search page."""
    result = fetch_collections(token)
    if "status" in result and not result["status"]:
        return {"error": result}

    context = {
        "collections": [c["name"] for c in result["body"]["collections"]],
        "generative_models": fetch_generative_models(token),
    }
    context.update(fetch_collection_filters(token, collection_name))
    return context


def parse_search_form(form: FormData) -> dict:
    """Build (search_options, answer_options, run_models_options) from the HTML
    form. Mirrors streamlit ui_utils.prepare_search_params."""
    results_count = int(form.get("results_count") or constants.DEFAULT_MAX_RESULTS)
    rerank_results = form.get("rerank_results") is not None
    hybrid_search = form.get("hybrid_search") is not None
    use_content_supervisor = form.get("use_content_supervisor") is not None
    # The RAG supervisor switch defaults to "on" (same as in the Streamlit UI),
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

    The engine returns the results as a dict keyed by document/result id
    (that is why the Streamlit UI transposed them); a flat list is accepted as
    well so a different response shape does not break the page.
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
        # has to stay visible in the table (Streamlit showed it as well).
        df = df.transpose()
        df.index.name = index_label
        df = df.reset_index()
    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=False)
    return df.to_dict(orient="records")


def prepare_stats_dataframe(stats) -> list:
    """Mirror of streamlit: transposed dataframe sorted by score_weighted."""
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


# --- Home (streamlit_ui/Home.py) -------------------------------------------- #
@app.get("/home", include_in_schema=False)
def home(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect
    return render_page(request, "home.html")


# --- Login (streamlit_ui/pages/0_Login.py) ---------------------------------- #
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
    context = fetch_manage_collection_context(
        get_token(request), kb_collection_name(request, collection_name)
    )
    if "error" in context:
        return render_api_error(request, context["error"])
    return render_page(request, name, **{**context, **extra})


# --- Collections (streamlit_ui/pages/1_New_Collection.py) ------------------- #
def render_collections_page(request: Request, **context) -> HTMLResponse:
    """List of the collections plus the form that creates a new one."""
    token = get_token(request)
    embedders = sse_api_engine.embedders(token=token)
    if not isinstance(embedders, list):
        return render_api_error(request, embedders)
    rerankers = sse_api_engine.rerankers(token=token)
    if not isinstance(rerankers, list):
        return render_api_error(request, rerankers)

    data = fetch_collection_rows(token)
    if "error" in data:
        return render_api_error(request, data["error"])

    remembered = kb_collection_name(request)
    names = [row["name"] for row in data["collections"]]
    return render_page(
        request,
        "collections.html",
        embedders=embedders,
        rerankers=rerankers,
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
    }

    result = sse_api_engine.new_collection(
        token=token, collection_params=collection_params
    )
    if not result.get("status"):
        return render_api_error(request, result)

    return render_collections_page(
        request,
        success=translator(request)("collections.created"),
        created=collection_params,
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
    )
    if not result.get("status"):
        return render_api_error(request, result)

    body = result.get("body") or {}
    indexed_chunks = body.get("indexed_chunks", 1)

    return render_kb_page(
        request,
        "upload_documents.html",
        collection_name,
        add_method="text",
        success=t("manage.add_text_success", chunks=indexed_chunks),
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


# --- Upload documents (streamlit_ui/pages/2_Upload_Documents.py) ------------ #
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
    )
    if upload_response is None or upload_response.get("status") is False:
        return page(error=t("upload.error_upload"))

    return page(
        success=t("upload.success"),
        uploaded={
            "collection_name": collection_name,
            "files": len(uploaded_files),
            "max_tokens_in_chunk": indexing_options["max_tokens_in_chunk"],
            "number_of_overlap_tokens": indexing_options["number_of_overlap_tokens"],
        },
    )


# --- Semantic search engine (streamlit_ui/pages/3_Semantic_Search_Engine.py)  #
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
    return render_page(
        request,
        "search.html",
        selected_collection=collection_name,
        prompt=params.value("prompt", ""),
        search_params=params.for_collection(collection_name),
        history=fetch_search_history(token, collection_name),
        **data,
    )


@app.get("/search/params/reset", include_in_schema=False)
def search_params_reset(request: Request):
    """Forget the remembered sidebar options (back to the defaults)."""
    redirect = require_login(request)
    if redirect is not None:
        return redirect
    set_state(request, **{LAST_SEARCH_PARAMS: None})
    collection_name = request.query_params.get("collection_name", "")
    url = "/search"
    if collection_name:
        url += "?" + urlencode({"collection_name": collection_name})
    return RedirectResponse(url=url, status_code=303)


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
        # Extractive QA was commented out in the Streamlit UI as well
        # (pages/3_Semantic_Search_Engine.py: prepare_extractive_qa_results)
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
def search_history_panel(request: Request, collection_name: str = ""):
    """History panel of a collection (HTML fragment, used when it changes)."""
    if require_login(request) is not None:
        return JSONResponse({"status": False, "error": "unauthorized"}, status_code=401)
    history = fetch_search_history(get_token(request), collection_name)
    html = templates.env.get_template("partials/search_history.html").render(
        t=translator(request),
        history=history,
        selected_collection=collection_name,
        history_open=True,
    )
    return JSONResponse(
        {"status": history is not None, "count": len(history or []), "html": html}
    )


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


# --- JSON endpoints (used by the page JS, no Streamlit counterpart) --------- #
@app.get("/api/options", include_in_schema=False)
def api_options(request: Request, collection_name: str = ""):
    redirect_target = require_login(request)
    if redirect_target is not None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    filters = fetch_collection_filters(get_token(request), collection_name)
    return JSONResponse({"status": True, "body": filters})


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
