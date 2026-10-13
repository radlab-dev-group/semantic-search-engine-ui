"""
FastAPI + Jinja2 twin of the Streamlit UI (streamlit_ui/).

Pages of the Streamlit app mapped to routes:

    streamlit_ui/Home.py                            -> /home
    streamlit_ui/pages/0_Login.py                   -> /login, /logout
    streamlit_ui/pages/1_New_Collection.py          -> /collections/new
    streamlit_ui/pages/2_Upload_Documents.py        -> /documents/upload
    streamlit_ui/pages/3_Semantic_Search_Engine.py  -> /search, /search/rate
    streamlit_ui/pages/4_Conversational_Search.py   -> /chat, /chat/message, /chat/clear

Run with:
    cd fastapi_ui && bash run.sh
or:
    cd fastapi_ui && uvicorn server:app --host 0.0.0.0 --port 8000
"""

import datetime
import json
import logging
import os

import pandas as pd
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, RedirectResponse

from core import constants
from core.api import SemanticSearchEngineAPI
from core.env_utils import bool_env_value
from core.state_store import CHAT, CHAT_ID, CS_RAG, LAST_QUERY_RESPONSE_ID
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

# Voice input (the Streamlit app showed streamlit_mic_recorder when it was
# served over HTTPS or on localhost; browsers allow the Web Speech API only in
# secure contexts, hence the same rule here).
templates.env.globals["speech_input"] = bool_env_value("UI_SPEECH_INPUT")

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


def clear_chat_session(request: Request) -> None:
    clear_state(request)


def get_chat(request: Request) -> list:
    return get_state(request).get(CHAT) or []


def get_chat_id(request: Request):
    return get_state(request).get(CHAT_ID)


def get_cs_rag(request: Request) -> dict:
    return get_state(request).get(CS_RAG) or {}


def get_last_response_id(request: Request):
    return get_state(request).get(LAST_QUERY_RESPONSE_ID)


def render_page(
    request: Request, name: str, status_code: int = 200, **context
) -> HTMLResponse:
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


def fetch_generative_models(token: str) -> list:
    generative_models_result = sse_api_engine.list_generative_models(token=token)
    if generative_models_result.get("status"):
        return list(generative_models_result["body"].keys())
    return []


def fetch_page_context(token: str, collection_name: str = "") -> dict:
    """All data required to render the search/chat pages."""
    result = fetch_collections(token)
    if "status" in result and not result["status"]:
        return {"error": result}

    context = {
        "collections": [c["name"] for c in result["body"]["collections"]],
        "generative_models": fetch_generative_models(token),
    }
    context.update(fetch_collection_filters(token, collection_name))
    return context


def parse_search_form(form: FormData, force_generative: bool = False) -> dict:
    """Build (search_options, answer_options, run_models_options) from the HTML
    form. Mirrors streamlit ui_utils.prepare_search_params."""
    results_count = int(form.get("results_count") or constants.DEFAULT_MAX_RESULTS)
    rerank_results = form.get("rerank_results") is not None
    use_content_supervisor = form.get("use_content_supervisor") is not None
    # The RAG supervisor switch defaults to "on" (same as in the Streamlit UI),
    # so an absent field (checkbox not rendered) means True.
    if "use_rag_supervisor" in form:
        use_rag_supervisor = form.get("use_rag_supervisor") is not None
    else:
        use_rag_supervisor = True
    return_with_factored_fields = form.get("return_with_factored_fields") is not None
    use_qa_extractive = form.get("use_qa_extractive") is not None
    use_gen_qa = force_generative or form.get("use_qa_generative") is not None
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
            error="Invalid username or password!",
            username=username,
        )

    request.session["sse_token"] = token
    request.session["sse_login"] = username
    clear_chat_session(request)
    return RedirectResponse(url="/search", status_code=303)


@app.get("/logout", include_in_schema=False)
def logout(request: Request):
    clear_chat_session(request)
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# --- New collection (streamlit_ui/pages/1_New_Collection.py) ---------------- #
@app.get("/collections/new", include_in_schema=False)
def new_collection_page(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    embedders = sse_api_engine.embedders(token=get_token(request))
    if not isinstance(embedders, list):
        return render_api_error(request, embedders)
    rerankers = sse_api_engine.rerankers(token=get_token(request))
    if not isinstance(rerankers, list):
        return render_api_error(request, rerankers)

    return render_page(
        request, "new_collection.html", embedders=embedders, rerankers=rerankers
    )


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

    return render_page(
        request,
        "new_collection.html",
        embedders=sse_api_engine.embedders(token=token),
        rerankers=sse_api_engine.rerankers(token=token),
        success=(
            f"Collection {collection_params['collection_name']} has been created! "
            f"Go to 'Upload Documents' and choose "
            f"{collection_params['collection_name']} to add documents to collection!"
        ),
        result_json=json.dumps(result, indent=2),
    )


# --- Upload documents (streamlit_ui/pages/2_Upload_Documents.py) ------------ #
@app.get("/documents/upload", include_in_schema=False)
def upload_documents_page(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    data = fetch_page_context(get_token(request))
    if "error" in data:
        return render_api_error(request, data["error"])
    return render_page(request, "upload_documents.html", **data)


@app.post("/documents/upload", include_in_schema=False)
def upload_documents_submit(request: Request, form: FormData = Depends(parsed_form)):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    collection_name = form.get("collection_name", "")
    uploaded_files = form.getlist("files[]")

    def page(**kwargs):
        data = fetch_page_context(token, collection_name)
        if "error" in data:
            return render_api_error(request, data["error"])
        return render_page(
            request,
            "upload_documents.html",
            selected_collection=collection_name,
            **{**data, **kwargs},
        )

    if not len(uploaded_files):
        return page(error="There are no files to upload!")

    indexing_options = {
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

    upload_response = sse_api_engine.upload_files(
        token=token,
        files_to_upload=uploaded_files,
        collection_name=collection_name,
        indexing_options=indexing_options,
    )
    if upload_response is None or upload_response.get("status") is False:
        return page(
            error="Problem while uploading files to engine backend",
            result_json=json.dumps(upload_response, indent=2),
        )

    return page(
        success=(
            "Files are uploaded and indexed! Go to `Semantic Search Engine` "
            "and test ask about knowledge from the indexed documents!"
        ),
        result_json=json.dumps(upload_response, indent=2),
    )


# --- Semantic search engine (streamlit_ui/pages/3_Semantic_Search_Engine.py)  #
@app.get("/search", include_in_schema=False)
def search_page(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    data = fetch_page_context(get_token(request))
    if "error" in data:
        return render_api_error(request, data["error"])
    return render_page(request, "search.html", **data)


@app.post("/search", include_in_schema=False)
def search_submit(request: Request, form: FormData = Depends(parsed_form)):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    collection_name = form.get("collection_name", "")
    question = form.get("question", "")
    prompt = form.get("prompt", "")

    options = parse_search_form(form)
    search_options = options["search_options"]
    answer_options = options["answer_options"]
    run_models_options = options["run_models_options"]

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
            **{**data, **kwargs},
        )

    if not question or not len(question.strip()):
        return page(error="Enter a sentence to search!")

    results = sse_api_engine.search_answer_with_options(
        token=token,
        collection_name=collection_name,
        question=question,
        options=search_options,
    )
    if results.get("status") is False:
        return render_api_error(request, results)

    if "body" not in results or "results" not in results["body"]:
        return page(error="Engine returned no results section!")

    if not len(results["body"]["results"]):
        return page(warning="No results found!")

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
        return page(error=f"Cannot prepare results: {exc}")

    qa_results = []
    if run_models_options["use_qa_extractive"]:
        # Extractive QA was commented out in the Streamlit UI as well
        # (pages/3_Semantic_Search_Engine.py: prepare_extractive_qa_results)
        pass

    qa_gen_results = None
    qa_gen_results_time = None
    if run_models_options["use_qa_generative"]:
        qa_gen_results = sse_api_engine.generative_answer_from_results(
            token=token,
            query_response_id=body["query_response_id"],
            query_prompt=prompt,
            query_options=answer_options,
        )
        if not qa_gen_results.get("status"):
            return render_api_error(request, qa_gen_results)
        qa_gen_results = qa_gen_results["body"]
        qa_gen_results_time = format_generation_time(
            qa_gen_results.get("generation_time")
        )
        set_state(request, **{LAST_QUERY_RESPONSE_ID: qa_gen_results["response_id"]})

    return page(
        stats=stats,
        detailed=detailed,
        qa_results=qa_results,
        qa_gen_results=qa_gen_results,
        qa_gen_results_time=qa_gen_results_time,
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
    return RedirectResponse(url="/search", status_code=303)


# --- Conversational search (streamlit_ui/pages/4_Conversational_Search.py) -- #
@app.get("/chat", include_in_schema=False)
def chat_page(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    data = fetch_page_context(get_token(request))
    if "error" in data:
        return render_api_error(request, data["error"])

    cs_rag = get_cs_rag(request)
    return render_page(
        request,
        "chat.html",
        chat=get_chat(request),
        chat_id=get_chat_id(request),
        cs_rag=cs_rag,
        general_stats=prepare_optional_stats(cs_rag.get("general_stats")),
        detailed_stats=prepare_optional_stats(
            cs_rag.get("detailed_results"), detailed=True
        ),
        **data,
    )


@app.post("/chat/message", include_in_schema=False)
def chat_message(request: Request, form: FormData = Depends(parsed_form)):
    redirect = require_login(request)
    if redirect is not None:
        return redirect

    token = get_token(request)
    user_message = (form.get("message") or "").strip()
    collection_name = form.get("collection_name", "")

    if not len(user_message):
        return RedirectResponse(url="/chat", status_code=303)

    options = parse_search_form(form, force_generative=True)
    search_options = options["search_options"]
    answer_options = options["answer_options"]

    chat_id = get_chat_id(request)
    if chat_id is None:
        chat_id = sse_api_engine.new_chat(
            token=token,
            collection_name=collection_name,
            options=answer_options,
            search_options=search_options,
        )

    api_response = sse_api_engine.add_user_message_to_chat(
        token=token,
        chat_id=chat_id,
        user_message=user_message,
        options=answer_options,
        search_options=search_options,
        collection_name=collection_name,
    )

    whole_chat = api_response["history"]
    last_state = api_response["last_state"]

    cs_rag = {}
    if last_state is not None and len(last_state):
        last_state = last_state[0]
        rag_message_state = last_state.get("rag_message_state")
        if rag_message_state is not None:
            sse_response = rag_message_state.get("sse_response") or {}
            cs_rag = {
                "extracted_query": rag_message_state.get("extracted_query"),
                "general_stats": sse_response.get("general_stats_json"),
                "detailed_results": sse_response.get("detailed_results_json"),
            }
        content_supervisor_state = last_state.get("content_supervisor_state")
        if content_supervisor_state:
            cs_rag["content_supervisor_state"] = content_supervisor_state

    set_state(
        request,
        **{
            CHAT: whole_chat,
            CHAT_ID: chat_id,
            CS_RAG: cs_rag,
        },
    )

    data = fetch_page_context(token, collection_name)
    if "error" in data:
        return render_api_error(request, data["error"])

    return render_page(
        request,
        "chat.html",
        chat=whole_chat,
        chat_id=chat_id,
        cs_rag=cs_rag,
        general_stats=prepare_optional_stats(cs_rag.get("general_stats")),
        detailed_stats=prepare_optional_stats(
            cs_rag.get("detailed_results"), detailed=True
        ),
        generation_time=format_generation_time(api_response.get("generation_time")),
        percentage_rank_mass=answer_options["percentage_rank_mass"],
        selected_collection=collection_name,
        **data,
    )


@app.post("/chat/clear", include_in_schema=False)
def chat_clear(request: Request):
    redirect = require_login(request)
    if redirect is not None:
        return redirect
    clear_chat_session(request)
    return RedirectResponse(url="/chat", status_code=303)


def prepare_optional_stats(stats, detailed: bool = False) -> list | None:
    if not stats:
        return None
    try:
        if detailed:
            return prepare_detailed_results_dataframe(stats)
        return prepare_stats_dataframe(stats)
    except Exception:  # noqa: BLE001
        logger.exception("Cannot prepare RAG stats table")
        return None


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
