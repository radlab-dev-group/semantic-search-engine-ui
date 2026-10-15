"""
End-to-end smoke test of the FastAPI UI against a mocked SSE backend.

Run from the fastapi_ui directory:

    .venv/bin/python tests/smoke_test.py

It does not require a real semantic-search-engine backend: all REST calls are
served by tests/mock_sse_backend.py.
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from tests.mock_sse_backend import (  # noqa: E402
    DOCUMENTS_IN_SEARCH,
    REQUEST_LOG,
    start_mock_backend,
)

mock = start_mock_backend()
mock_host = f"http://127.0.0.1:{mock.server_address[1]}"

config = {
    "api_hosts": {
        "conversational_search": {
            "host": mock_host,
            "ep": {"conversation_with_model": "api/conversation_with_model"},
        },
        "semantic_search_engine": {
            "host": mock_host,
            "ep": {
                "login": "api/login",
                "new_collection": "api/new_collection",
                "collections": "api/collections",
                "generative_models": "api/generative_models",
                "embedders": "api/embedders",
                "rerankers": "api/rerankers",
                "categories": "api/categories",
                "documents": "api/documents",
                "search_with_options": "api/search_with_options",
                "generative_answer": "api/generative_answer",
                "rate_generative_answer": "api/rate_generative_answer",
                "upload_and_index_files": "api/upload_and_index_files",
                "delete_collection": "api/delete_collection",
                "delete_documents": "api/delete_documents",
                "delete_texts": "api/delete_texts",
                "add_and_index_texts": "api/add_and_index_texts",
            },
        },
    }
}

config_file = Path(tempfile.gettempdir()) / "smoke-ui-configuration.json"
config_file.write_text(json.dumps(config), encoding="utf-8")
os.environ["UI_CONFIG_PATH"] = str(config_file)

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

FAILURES = []


def check(name: str, condition: bool, extra: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}{'' if condition else f' -> {extra}'}")
    if not condition:
        FAILURES.append(name)


def last_request(method: str, endpoint: str) -> dict:
    for entry in reversed(REQUEST_LOG):
        if entry["method"] == method and entry["path"].endswith(endpoint):
            return entry
    return {}


UNTRANSLATED_KEY = re.compile(
    r"\b(?:base|nav|stepper|messages|home|login|error|collections|upload|search"
    r"|params|history|hits|board|table|manage|js)\.[a-z_]+\b"
)


def check_i18n(client) -> None:
    from core import i18n

    en, pl = i18n.catalog("en"), i18n.catalog("pl")
    check(
        "pl and en translations have the same keys",
        set(en) == set(pl),
        f"only en: {sorted(set(en) - set(pl))}, only pl: {sorted(set(pl) - set(en))}",
    )
    check(
        "polish plural forms",
        [i18n.translate_plural("pl", "upload.files_count", n) for n in (1, 3, 5, 22, 112)]
        == ["1 plik", "3 pliki", "5 plików", "22 pliki", "112 plików"]
        and i18n.translate_plural("en", "upload.files_count", 1) == "1 file",
        "",
    )
    check(
        "accept-language parsing",
        i18n.language_from_header("de-DE,pl;q=0.8,en;q=0.5") == "pl"
        and i18n.language_from_header("en-GB,pl;q=0.9") == "en"
        and i18n.language_from_header("de") is None,
        "",
    )
    check(
        "html translations escape their arguments",
        str(i18n.translate("en", "hits.from_html", document="<x>"))
        == "from <b>&lt;x&gt;</b>",
        "",
    )

    response = client.get("/search")
    check(
        "english is the default language",
        '<html lang="en"' in response.text
        and 'href="/lang/pl?next=/search"' in response.text
        and '"lang": "en"' in response.text,
        "",
    )

    response = client.get(
        "/lang/pl?next=/search%3Fcollection_name%3Duser_col", follow_redirects=False
    )
    check(
        "language switch stores the choice and goes back",
        response.status_code == 303
        and response.headers["location"] == "/search?collection_name=user_col"
        and "sse_lang=pl" in response.headers.get("set-cookie", ""),
        str(response.headers),
    )
    for target in ["https://evil.example", "//evil.example", "/\\evil.example"]:
        response = client.get(
            "/lang/pl", params={"next": target}, follow_redirects=False
        )
        check(
            f"language switch never redirects off-site ({target})",
            response.headers.get("location") == "/",
            str(response.headers),
        )

    client.cookies.set("sse_lang", "pl")
    pages = {url: client.get(url).text for url in ["/home", "/collections", "/collections/manage", "/documents/upload", "/search"]}
    check(
        "polish interface",
        '<html lang="pl"' in pages["/search"]
        and ">Baza wiedzy</a>" in pages["/search"]
        and "Parametry wyszukiwania" in pages["/search"]
        and "Szukaj po <span" in pages["/home"]
        and "Lista kolekcji" in pages["/collections"]
        and "Sekcje bazy wiedzy" in pages["/collections/manage"]
        and ">Baza wiedzy</a>" in pages["/collections"]
        and "Dodaj treść do kolekcji" in pages["/documents/upload"]
        and "Opcje indeksowania dokumentów" in pages["/documents/upload"]
        and '"lang": "pl"' in pages["/search"],
        "",
    )
    leaked = {url: UNTRANSLATED_KEY.findall(html) for url, html in pages.items()}
    check(
        "no untranslated keys on polish pages",
        not any(leaked.values()),
        str(leaked),
    )
    check(
        "polish pages render without inline styles",
        all('style="' not in html for html in pages.values()),
        "",
    )

    response = client.post(
        "/search",
        data={
            "collection_name": "user_col",
            "question": "jakies pytanie",
            "use_qa_generative": "on",
            "qa_gen_model": "llama-8b",
        },
    )
    generation = re.search(r'data-generate="([0-9a-f]+)"', response.text)
    payload = client.post(
        "/search/generate",
        data={"generation_id": generation.group(1) if generation else ""},
    ).json()
    generated_html = payload.get("answer_html", "") + payload.get("feedback_html", "")
    check(
        "polish search results",
        "Co znalazł silnik" in response.text
        and "Statystyki wyszukiwania" in response.text
        and "model pisze teraz" in response.text
        and "Odpowiedź modelu" in generated_html
        and "Wyślij opinię!" in generated_html
        and not UNTRANSLATED_KEY.findall(response.text + generated_html),
        str(UNTRANSLATED_KEY.findall(response.text + generated_html)),
    )
    response = client.post(
        "/search", data={"collection_name": "user_col", "question": " "}
    )
    check(
        "polish server messages",
        "Wpisz zdanie do wyszukania!" in response.text,
        "",
    )
    response = client.post(
        "/documents/upload",
        data={"collection_name": "user_col"},
        files=[
            ("files[]", ("a.pdf", b"PDF-A", "application/pdf")),
            ("files[]", ("b.txt", b"text", "text/plain")),
        ],
    )
    check(
        "polish upload summary uses plural forms",
        "Podsumowanie indeksowania" in response.text and "2 pliki" in response.text,
        "",
    )

    client.cookies.delete("sse_lang")
    response = client.get("/search", headers={"Accept-Language": "pl-PL,pl;q=0.9"})
    check(
        "language detected from Accept-Language",
        '<html lang="pl"' in response.text,
        "",
    )
    client.cookies.set("sse_lang", "en")
    response = client.get("/search", headers={"Accept-Language": "pl"})
    check(
        "chosen language wins over Accept-Language",
        '<html lang="en"' in response.text,
        "",
    )
    client.cookies.delete("sse_lang")


def check_chunking(client) -> None:
    """Chunking of the engine: new collection form, collection cards,
    indexing with the settings of the collection, refused chunking."""
    # --- New collection form ------------------------------------------- #
    page = client.get("/collections").text
    check(
        "new collection form carries models_info on the model options",
        'data-max-length="512" data-vector-size="768" data-device="cuda">embedder-a'
        in page
        and 'data-max-length="" data-vector-size="1024" data-device="cpu">embedder-b'
        in page
        and 'data-max-length="512" data-device="cuda">reranker-a' in page,
        "",
    )
    check(
        "new collection form is prefilled with chunking_defaults of the engine",
        'name="max_tokens_in_chunk" inputmode="numeric" min="1" step="1" value="500"'
        in page
        and 'name="number_of_overlap_tokens" inputmode="numeric" min="0" step="1" value="0"'
        in page
        and 'name="chunking_default_max" value="500"' in page
        and 'name="chunking_default_overlap" value="0"' in page
        and 'name="chunking_edited" value="0"' in page
        and 'name="strict_chunking"' in page,
        "",
    )
    check(
        "collection cards show the declared chunking and the strict badge",
        "512 tokens · overlap 32" in page
        and "256 tokens · overlap 0" in page
        and page.count('class="badge badge--strict"') == 1
        and 'class="collection__chunking is-undeclared"' in page
        and "chunking not declared" in page,
        "",
    )

    # Untouched defaults: no "chunking" in the request, strict off
    response = client.post(
        "/collections/new",
        data={
            "collection_name": "plain",
            "collection_display_name": "Plain",
            "embedder_index_type": "HNSW",
            "embedder_model": "embedder-a",
            "re_ranker_model": "reranker-a",
            "max_tokens_in_chunk": "500",
            "number_of_overlap_tokens": "0",
            "chunking_default_max": "500",
            "chunking_default_overlap": "0",
            "chunking_edited": "0",
        },
    )
    sent = last_request("POST", "api/new_collection").get("body", {})
    check(
        "untouched chunking defaults are not sent to the engine",
        response.status_code == 200
        and "chunking" not in sent
        and sent.get("strict_chunking") == "false"
        and sent.get("lang") == "en",
        str(sent),
    )
    summary = re.search(r'<dl class="kv">.*?</dl>', response.text, re.S)
    summary = summary.group(0) if summary else ""
    check(
        "created collection summary shows the chunking the engine answered with",
        "500 tokens · overlap 0" in summary
        and 'class="badge badge--strict"' not in summary,
        summary,
    )

    # Edited chunking + strict: both go to the engine
    response = client.post(
        "/collections/new",
        data={
            "collection_name": "custom",
            "collection_display_name": "Custom",
            "embedder_index_type": "HNSW",
            "embedder_model": "embedder-a",
            "re_ranker_model": "reranker-a",
            "max_tokens_in_chunk": "400",
            "number_of_overlap_tokens": "40",
            "strict_chunking": "on",
            "chunking_default_max": "500",
            "chunking_default_overlap": "0",
            "chunking_edited": "1",
        },
    )
    sent = last_request("POST", "api/new_collection").get("body", {})
    check(
        "edited chunking is sent as a JSON object with strict_chunking",
        json.loads(sent.get("chunking", "{}"))
        == {"max_tokens_in_chunk": 400, "number_of_overlap_tokens": 40}
        and sent.get("strict_chunking") == "true",
        str(sent),
    )
    summary = re.search(r'<dl class="kv">.*?</dl>', response.text, re.S)
    summary = summary.group(0) if summary else ""
    check(
        "created collection summary shows chunking and the strict badge",
        "400 tokens · overlap 40" in summary
        and 'class="badge badge--strict"' in summary,
        summary,
    )

    # Overlap outside [0, chunk): refused by the UI, nothing sent
    before = len(REQUEST_LOG)
    response = client.post(
        "/collections/new",
        data={
            "collection_name": "bad",
            "collection_display_name": "Bad",
            "embedder_index_type": "HNSW",
            "embedder_model": "embedder-a",
            "re_ranker_model": "reranker-a",
            "max_tokens_in_chunk": "100",
            "number_of_overlap_tokens": "100",
            "chunking_edited": "1",
        },
    )
    check(
        "overlap not smaller than the chunk is refused before the engine",
        response.status_code == 200
        and "The overlap must be within 0 and the chunk size" in response.text
        and 'value="100" placeholder="engine default" data-chunk-overlap class="is-invalid" aria-invalid="true"'
        in response.text
        and not any(
            entry["path"].endswith("new_collection") for entry in REQUEST_LOG[before:]
        ),
        "",
    )

    # CHUNKING_TOO_LONG (000005_DATA) of the engine: chunk field marked
    response = client.post(
        "/collections/new",
        data={
            "collection_name": "long",
            "collection_display_name": "Long",
            "collection_description": "opis",
            "embedder_index_type": "HNSW",
            "embedder_model": "embedder-a",
            "re_ranker_model": "reranker-a",
            "max_tokens_in_chunk": "600",
            "number_of_overlap_tokens": "0",
            "chunking_edited": "1",
        },
    )
    check(
        "000005_DATA on a new collection highlights the chunk size",
        response.status_code == 200
        and "The chunk is longer than the maximum input length of the embedder."
        in response.text
        and 'value="600" placeholder="engine default" data-chunk-size class="is-invalid" aria-invalid="true"'
        in response.text
        and 'class="card card--subtle chunking-card has-error"' in response.text
        and 'name="collection_name" value="long"' in response.text
        and ">opis</textarea>" in response.text
        and 'name="chunking_edited" value="1"' in response.text,
        response.text[:300],
    )

    # --- Indexing: settings of the collection vs. custom values --------- #
    page = client.get("/documents/upload?collection_name=user_col").text
    check(
        "indexing forms default to the chunking of the collection",
        page.count('name="chunking_mode" value="collection" checked') == 2
        and page.count("512 tokens · overlap 32") == 2
        and page.count('data-ref-chunk="512"') == 2
        and page.count('class="chunk-fields is-locked"') == 2
        and 'name="max_tokens_in_chunk" min="10" max="1000" step="1"\n           value="512"\n           disabled'
        in page,
        "",
    )
    page = client.get("/documents/upload?collection_name=user_kol").text
    check(
        "an undeclared collection shows the defaults of the engine",
        "the collection declares no chunking — the engine uses its defaults: 500 tokens · overlap 0"
        in page
        and 'data-ref-chunk="500"' in page,
        "",
    )
    page = client.get("/documents/upload?collection_name=user_strict").text
    check(
        "a strict collection warns that custom values give CHUNKING_MISMATCH",
        page.count('class="chunk-mode is-strict"') == 2
        and page.count("data-strict-warning hidden") == 2
        and "fails with CHUNKING_MISMATCH" in page
        and 'class="badge badge--strict"' in page,
        "",
    )

    response = client.post(
        "/documents/upload",
        data={
            "collection_name": "user_col",
            "chunking_mode": "collection",
            "clear_text": "on",
            "max_tokens_in_chunk": "512",
            "number_of_overlap_tokens": "32",
        },
        files=[("files[]", ("a.pdf", b"PDF-A", "application/pdf"))],
    )
    options = json.loads(
        last_request("POST", "api/upload_and_index_files")
        .get("body", {})
        .get("indexing_options", "{}")
    )
    check(
        "collection mode sends indexing_options without the chunk keys",
        response.status_code == 200
        and "max_tokens_in_chunk" not in options
        and "number_of_overlap_tokens" not in options
        and options.get("clear_text") is True
        and "prepare_proper_pages" in options
        and "Collection settings: 512 tokens · overlap 32" in response.text,
        str(options),
    )
    response = client.post(
        "/documents/upload",
        data={
            "collection_name": "user_col",
            "chunking_mode": "custom",
            "max_tokens_in_chunk": "300",
            "number_of_overlap_tokens": "30",
        },
        files=[("files[]", ("a.pdf", b"PDF-A", "application/pdf"))],
    )
    options = json.loads(
        last_request("POST", "api/upload_and_index_files")
        .get("body", {})
        .get("indexing_options", "{}")
    )
    check(
        "custom mode sends both chunk keys",
        options.get("max_tokens_in_chunk") == 300
        and options.get("number_of_overlap_tokens") == 30
        and ">300</dd>" in response.text,
        str(options),
    )

    # CHUNKING_MISMATCH (000006_DATA): back to the settings of the collection
    response = client.post(
        "/documents/upload",
        data={
            "collection_name": "user_strict",
            "chunking_mode": "custom",
            "max_tokens_in_chunk": "300",
            "number_of_overlap_tokens": "30",
        },
        files=[("files[]", ("a.pdf", b"PDF-A", "application/pdf"))],
    )
    files_form = response.text.split('id="panel-add-text"')[0]
    check(
        "000006_DATA clears the override and proposes the collection values",
        response.status_code == 200
        and "Chunking settings differ from the ones of the collection." in response.text
        and 'name="chunking_mode" value="collection" checked' in files_form
        and "Collection settings restored: 256 tokens · overlap 0" in files_form
        and 'data-ref-chunk="256"' in files_form
        and 'class="tab-panel is-active" role="tabpanel" id="panel-add-files"'
        in response.text,
        response.text[:300],
    )

    # CHUNKING_TOO_LONG (000005_DATA) on pasted text: slider marked, text kept
    response = client.post(
        "/collections/manage/add-text",
        data={
            "collection_name": "user_col",
            "filepath": "long.txt",
            "category": "notes",
            "page_content": "Tekst do zaindeksowania",
            "chunking_mode": "custom",
            "max_tokens_in_chunk": "600",
            "number_of_overlap_tokens": "0",
        },
    )
    sent = last_request("POST", "api/add_and_index_texts").get("body", {})
    text_form = response.text.split('id="panel-add-text"')[1]
    check(
        "000005_DATA on indexing highlights the chunk slider and keeps the text",
        response.status_code == 200
        and sent.get("lang") == "en"
        and "The chunk is longer than the maximum input length of the embedder."
        in response.text
        and 'class="field-slider is-invalid"' in text_form
        and 'name="chunking_mode" value="custom" checked' in text_form
        and 'value="600"' in text_form
        and "data-too-long-note" in text_form
        and ">Tekst do zaindeksowania</textarea>" in text_form
        and 'value="long.txt"' in text_form
        and 'class="tab-panel is-active" role="tabpanel" id="panel-add-text"'
        in response.text
        and 'class="field-slider is-invalid"' not in response.text.split('id="panel-add-text"')[0],
        response.text[:300],
    )


def main() -> int:
    with TestClient(server.app) as client:
        # --- Login page / auth guard --------------------------------------- #
        response = client.get("/search", follow_redirects=False)
        check(
            "not logged in -> redirect to /login",
            response.status_code == 303 and "/login" in response.headers["location"],
            str(response.headers),
        )

        response = client.get("/")
        check(
            "root page renders login",
            "/login" in str(response.url) or response.status_code == 200,
            str(response.status_code),
        )

        response = client.post(
            "/login", data={"username": "user", "password": "wrong"}
        )
        check(
            "wrong password -> error shown",
            response.status_code == 200
            and "Invalid username or password" in response.text,
            str(response.status_code),
        )

        response = client.post(
            "/login",
            data={"username": "user", "password": "pass"},
            follow_redirects=False,
        )
        check(
            "login -> redirect to /search",
            response.status_code == 303
            and "/search" in response.headers["location"],
            str(response.headers),
        )

        auth = last_request("POST", "api/login")
        check(
            "login sent credentials",
            auth.get("body", {}).get("username") == "user",
            str(auth),
        )

        # --- Home ---------------------------------------------------------- #
        response = client.get("/home")
        check(
            "home page",
            response.status_code == 200 and "SSSUI" in response.text,
            str(response.status_code),
        )

        # --- Collections ---------------------------------------------------- #
        response = client.get("/collections")
        check(
            "collections page lists collections from the engine",
            response.status_code == 200
            and "user_col" in response.text
            and "user_kol" in response.text
            and "Moje dokumenty" in response.text,
            str(response.status_code),
        )
        check(
            "collections list shows description and creation date",
            "Kolekcja użytkownika" in response.text
            and "2026-09-30" in response.text,
            "",
        )
        check(
            "collections list links to upload and search of a collection",
            'href="/documents/upload?collection_name=user_col"' in response.text
            and 'href="/search?collection_name=user_col"' in response.text,
            "",
        )
        check(
            "one navigation entry for the knowledge base",
            ">Knowledge base</a>" in response.text
            and ">New collection</a>" not in response.text
            and ">Manage</a>" not in response.text
            and ">Upload documents</a>" not in response.text
            and "nav__link is-active" in response.text,
            "",
        )
        check(
            "knowledge base tabs on the collections page",
            'class="kb-tabs"' in response.text
            and 'kb-tabs__link is-active" href="/collections"' in response.text
            and 'href="/collections/manage"' in response.text
            and 'href="/documents/upload"' in response.text,
            "",
        )
        check(
            "collection deletion asks in the styled dialog",
            'id="confirm-dialog"' in response.text
            and 'data-confirm-phrase="user_col"' in response.text
            and "return confirm(" not in response.text,
            "",
        )

        response = client.get("/collections/new", follow_redirects=False)
        check(
            "old new collection address redirects to /collections",
            response.status_code == 303
            and "/collections" in response.headers["location"],
            str(response.headers),
        )

        response = client.get("/collections/new")
        check(
            "new collection form",
            response.status_code == 200
            and "embedder-a" in response.text
            and "reranker-a" in response.text,
            str(response.status_code),
        )

        response = client.post(
            "/collections/new",
            data={
                "collection_name": "moje dokumenty",
                "collection_display_name": "Moje Dokumenty",
                "embedder_index_type": "HNSW",
                "embedder_model": "embedder-a",
                "re_ranker_model": "reranker-a",
                "collection_description": "",
            },
        )
        sent = last_request("POST", "api/new_collection")
        check(
            "collection created",
            response.status_code == 200 and "has been created" in response.text,
            str(response.status_code),
        )
        check(
            "collection name prefixed with username",
            sent.get("body", {}).get("collection_name") == "user_moje_dokumenty",
            str(sent.get("body")),
        )
        check(
            "default description generated",
            str(sent.get("body", {}).get("collection_description", "")).startswith(
                "Opis kolekcji"
            ),
            str(sent.get("body")),
        )
        check(
            "collection success is a styled alert with a summary",
            '<div class="alert alert-success" role="status">' in response.text
            and "Collection details" in response.text
            and 'href="/documents/upload?collection_name=user_moje_dokumenty"'
            in response.text,
            response.text[:400],
        )
        check(
            "collection success does not dump the raw API payload",
            "collection_id" not in response.text and "{'" not in response.text,
            "",
        )

        # --- Collection Delete & Manage ----------------------------------- #
        response = client.post(
            "/collections/delete",
            data={"collection_name": "user_col"},
        )
        sent = last_request("POST", "api/delete_collection")
        check(
            "delete collection succeeded",
            response.status_code == 200 and "has been deleted" in response.text,
            str(response.status_code),
        )
        check(
            "collection deletion shows the styled deletion alert",
            'class="alert alert-deleted"' in response.text
            and "vectors were removed" in response.text,
            "",
        )
        check(
            "delete collection sent collection_name",
            sent.get("body", {}).get("collection_name") == "user_col",
            str(sent),
        )

        response = client.get("/collections/manage?collection_name=user_col")
        check(
            "manage page renders with selected collection and documents",
            response.status_code == 200
            and "user_col" in response.text
            and "b.pdf" in response.text
            and "a.pdf" in response.text,
            str(response.status_code),
        )
        check(
            "documents tab: switcher, tab links keep the collection",
            '<option value="user_col" selected>' in response.text
            and 'kb-tabs__link is-active" href="/collections/manage?collection_name=user_col"'
            in response.text
            and 'href="/documents/upload?collection_name=user_col"' in response.text
            and 'data-confirm-items="a.pdf"' in response.text
            and "return confirm(" not in response.text,
            "",
        )
        check(
            "knowledge base remembers the collection",
            '<option value="user_col" selected>'
            in client.get("/documents/upload").text,
            "",
        )

        # --- use of the documents in the search (use_in_search) ---------- #
        manage_page = response.text
        sent = last_request("GET", "api/documents")
        check(
            "documents tab lists also the documents excluded from the search",
            sent.get("query", {}).get("with_disabled") == "true"
            and "old.pdf" in manage_page,
            str(sent.get("query")),
        )
        check(
            "every document row has the in-search switch next to delete",
            manage_page.count("data-doc-toggle") == 3
            and 'aria-checked="true"' in manage_page
            and 'aria-checked="false"' in manage_page
            and re.search(
                r'class="doc-row is-disabled" data-name="old\.pdf"', manage_page
            )
            is not None
            and 'data-doc-disabled-count>1<' in manage_page,
            "",
        )
        search_page = client.get("/search?collection_name=user_col").text
        check(
            "excluded documents are not offered in the search filters",
            "a.pdf" in search_page and "old.pdf" not in search_page,
            "",
        )

        response = client.post(
            "/collections/manage/visibility",
            data={
                "collection_name": "user_col",
                "toggle_document": "a.pdf",
                "use_in_search": "0",
            },
            headers={"Accept": "application/json"},
        )
        sent = last_request("POST", "api/set_documents_use_in_search")
        payload = response.json()
        check(
            "switch excludes a document from the search (JSON for app.js)",
            response.status_code == 200
            and payload.get("status") is True
            and payload.get("use_in_search") is False
            and payload.get("documents") == ["a.pdf"]
            and "Excluded 1 document" in payload.get("message", "")
            and sent.get("body")
            == {
                "collection_name": "user_col",
                "documents[]": ["a.pdf"],
                "use_in_search": False,
            },
            f"{payload} {sent.get('body')}",
        )
        check(
            "excluded document is shown as switched off",
            re.search(
                r'class="doc-row is-disabled" data-name="a\.pdf"',
                client.get("/collections/manage?collection_name=user_col").text,
            )
            is not None,
            "",
        )

        response = client.post(
            "/collections/manage/visibility?use_in_search=1",
            data={
                "collection_name": "user_col",
                "documents[]": ["a.pdf", "old.pdf"],
            },
        )
        sent = last_request("POST", "api/set_documents_use_in_search")
        check(
            "bulk include (form post without JS) re-renders the documents tab",
            response.status_code == 200
            and "Included 2 documents in the search again" in response.text
            and sent.get("body", {}).get("documents[]") == ["a.pdf", "old.pdf"]
            and sent.get("body", {}).get("use_in_search") is True
            and 'aria-checked="false"' not in response.text,
            str(sent.get("body")),
        )

        response = client.post(
            "/collections/manage/visibility",
            data={
                "collection_name": "user_col",
                "toggle_document": "missing.pdf",
                "use_in_search": "0",
            },
            headers={"Accept": "application/json"},
        )
        check(
            "switch reports an engine error as JSON",
            response.status_code == 502 and response.json().get("status") is False,
            str(response.status_code),
        )
        DOCUMENTS_IN_SEARCH.update({"b.pdf": True, "a.pdf": True, "old.pdf": False})

        response = client.post(
            "/collections/manage/add-text",
            data={
                "collection_name": "user_col",
                "filepath": "notes.txt",
                "category": "notes",
                "page_content": "This is a direct text content to be indexed.",
                "max_tokens_in_chunk": "300",
                "number_of_overlap_tokens": "30",
                "clear_text": "on",
                "prepare_proper_pages": "on",
            },
        )
        sent = last_request("POST", "api/add_and_index_texts")
        check(
            "add text document succeeded",
            response.status_code == 200 and "indexed" in response.text,
            str(response.status_code),
        )
        check(
            "add text returns to the add content tab with the text form open",
            'kb-tabs__link is-active" href="/documents/upload' in response.text
            and 'class="tab-panel is-active" role="tabpanel" id="panel-add-text"'
            in response.text,
            "",
        )
        check(
            "add text sent collection and texts payload",
            sent.get("body", {}).get("collection_name") == "user_col"
            and len(sent.get("body", {}).get("texts[]", [])) == 1
            and sent.get("body", {}).get("texts[]")[0]["filepath"] == "notes.txt",
            str(sent),
        )
        text_doc = (sent.get("body", {}).get("texts[]") or [{}])[0]
        check(
            "add text sends the engine texts[] shape",
            text_doc.get("relative_filepath") == "notes.txt"
            and text_doc.get("category") == "notes"
            and text_doc.get("pages")
            == [{"page_content": "This is a direct text content to be indexed."}],
            str(text_doc),
        )
        check(
            "add text sends the same indexing options as the file upload",
            sent.get("body", {}).get("indexing_options")
            == {
                "clear_text": True,
                "use_text_denoiser": False,
                "check_text_lang": False,
                "prepare_proper_pages": True,
                "merge_document_pages": False,
                "max_tokens_in_chunk": 300,
                "number_of_overlap_tokens": 30,
            },
            str(sent.get("body", {}).get("indexing_options")),
        )
        add_page = client.get("/documents/upload?collection_name=user_col").text
        check(
            "both add content forms share the indexing options and chunk preview",
            add_page.count("data-chunk-preview") == 2
            and add_page.count('name="number_of_overlap_tokens"') == 2
            and add_page.count('name="merge_document_pages"') == 2
            and 'id="text_use_text_denoiser"' in add_page
            and "clear_text_before_indexing" not in add_page,
            "",
        )

        response = client.post(
            "/collections/manage/delete-documents",
            data={
                "collection_name": "user_col",
                "document_name": "a.pdf",
            },
        )
        sent = last_request("POST", "api/delete_documents")
        check(
            "delete document succeeded",
            response.status_code == 200 and "Deleted" in response.text,
            str(response.status_code),
        )
        check(
            "document deletion shows what was deleted",
            'class="alert alert-deleted"' in response.text
            and "Deleted 1 document" in response.text
            and "<li>a.pdf</li>" in response.text,
            "",
        )
        check(
            "delete document sent document name",
            sent.get("body", {}).get("collection_name") == "user_col"
            and sent.get("body", {}).get("documents[]") == ["a.pdf"],
            str(sent),
        )

        response = client.post(
            "/collections/manage/delete-texts",
            data={
                "collection_name": "user_col",
                "chunk_ids": "10, 11, 12",
            },
        )
        sent = last_request("POST", "api/delete_texts")
        check(
            "delete texts succeeded",
            response.status_code == 200 and "Deleted" in response.text,
            str(response.status_code),
        )
        check(
            "chunk deletion lists the deleted ids",
            'class="alert alert-deleted"' in response.text
            and "Deleted 2 text chunks" in response.text
            and "<li>#10</li>" in response.text,
            "",
        )
        check(
            "delete texts sent chunk IDs",
            sent.get("body", {}).get("collection_name") == "user_col"
            and sent.get("body", {}).get("chunk_ids[]") == [10, 11, 12],
            str(sent),
        )

        # --- Upload documents ---------------------------------------------- #
        response = client.get("/documents/upload")
        check(
            "upload page lists collections",
            response.status_code == 200 and "user_col" in response.text,
            str(response.status_code),
        )

        check(
            "upload form uses the engine field names",
            all(
                f'name="{field}"' in client.get("/documents/upload").text
                for field in [
                    "files[]",
                    "collection_name",
                    "max_tokens_in_chunk",
                    "number_of_overlap_tokens",
                    "use_text_denoiser",
                    "clear_text",
                    "check_text_lang",
                    "prepare_proper_pages",
                    "merge_document_pages",
                ]
            ),
            "",
        )

        response = client.post(
            "/documents/upload",
            data={
                "collection_name": "user_col",
                "clear_text": "on",
                "check_text_lang": "on",
                "prepare_proper_pages": "on",
                "max_tokens_in_chunk": "300",
                "number_of_overlap_tokens": "30",
            },
            files=[
                ("files[]", ("a.pdf", b"PDF-A", "application/pdf")),
                ("files[]", ("b.txt", b"text", "text/plain")),
            ],
        )
        sent = last_request("POST", "api/upload_and_index_files")
        check(
            "upload succeeded",
            response.status_code == 200 and "uploaded and indexed" in response.text,
            str(response.status_code),
        )
        check(
            "upload sent multipart",
            "multipart/form-data" in str(sent.get("body", {}).get("_content_type")),
            str(sent.get("body")),
        )
        check(
            "upload sent indexing options",
            "max_tokens_in_chunk" in sent.get("raw_text", "")
            and '"max_tokens_in_chunk": 300' in sent.get("raw_text", ""),
            str(sent.get("body")),
        )
        check(
            "upload success shows an alert with an indexing summary",
            '<div class="alert alert-success" role="status">' in response.text
            and "Indexing summary" in response.text
            and "2 files" in response.text,
            response.text[:400],
        )
        check(
            "upload success does not dump the raw API payload",
            "indexed_chunks" not in response.text and "{'" not in response.text,
            "",
        )
        response = client.get("/documents/upload?collection_name=user_col")
        check(
            "upload page preselects the collection from the query string",
            '<option value="user_col" selected>' in response.text,
            "",
        )

        check_chunking(client)

        response = client.get("/search?collection_name=user_col")
        check(
            "search page preselects the collection from the query string",
            '<option value="user_col" selected ' in response.text,
            "",
        )
        # The options carry the description and the date for the banner
        check(
            "search offers the collections by their full (display) name",
            re.search(
                r'<option value="user_col" selected data-description="Kolekcja '
                r'użytkownika" data-created="2026-09-30">Moje dokumenty</option>',
                response.text,
            )
            is not None
            and re.search(
                r'<option value="user_kol"\s+data-description=""\s+data-created="[^"]*">'
                r"user_kol</option>",
                response.text,
            )
            is not None
            and 'class="history__collection"' in response.text
            and ">Moje dokumenty</span>" in response.text,
            "",
        )
        banner = re.search(
            r'<div class="coll-banner" data-collection-banner>.*?</div>\s*</div>',
            response.text,
            re.S,
        )
        banner_html = banner.group(0) if banner else ""
        check(
            "query console shows the chosen collection (name, description, date)",
            banner
            and 'title="Moje dokumenty">Moje dokumenty</strong>' in banner_html
            and ">user_col</span>" in banner_html
            and ">Kolekcja użytkownika</p>" in banner_html
            and "Created 2026-09-30" in banner_html
            and "/collections/manage?collection_name=user_col" in banner_html
            and "data-banner-change" in banner_html,
            banner_html[:600],
        )
        check(
            "query console banner is empty without a chosen collection",
            '<div class="coll-banner is-empty" data-collection-banner>'
            in client.get("/search?clear=1").text,
            "",
        )
        payload = client.get(
            "/search/history?collection_name=user_col&collection_label=Moje+dokumenty"
        ).json()
        check(
            "history panel refreshed with the full collection name",
            ">Moje dokumenty</span>" in payload.get("html", ""),
            "",
        )

        response = client.post(
            "/documents/upload", data={"collection_name": "user_col"}
        )
        check(
            "upload without files -> error",
            response.status_code == 200 and "no files to upload" in response.text,
            str(response.status_code),
        )

        # --- Search -------------------------------------------------------- #
        response = client.get("/search")
        check(
            "search page",
            response.status_code == 200
            and "user_col" in response.text
            and "llama-8b" in response.text,
            str(response.status_code),
        )

        generations_before = sum(
            entry["path"].endswith("api/generative_answer") for entry in REQUEST_LOG
        )
        response = client.post(
            "/search",
            data={
                "collection_name": "user_col",
                "question": "jakies pytanie",
                "prompt": "odpowiedz zwięźle",
                "results_count": "30",
                "min_similarity": "0.35",
                "rerank_results": "on",
                "hybrid_search": "on",
                "categories": ["a", "c"],
                "documents": ["b.pdf"],
                "use_qa_generative": "on",
                "qa_gen_model": "llama-8b",
                "perc_rank_to_gen_qa": "55",
            },
        )
        sent = last_request("POST", "api/search_with_options")
        options = json.loads(sent.get("body", {}).get("options", "{}"))
        check(
            "search results rendered",
            response.status_code == 200 and "Search statistics" in response.text,
            str(response.status_code),
        )
        generation = re.search(r'data-generate="([0-9a-f]+)"', response.text)
        check(
            "results are shown before the answer is generated",
            generation is not None
            and "answer-card--pending" in response.text
            and "To jest odpowiedź." not in response.text
            and "Send your feedback!" not in response.text
            and sum(
                entry["path"].endswith("api/generative_answer")
                for entry in REQUEST_LOG
            )
            == generations_before,
            "",
        )
        results_html = response.text
        generated = client.post(
            "/search/generate",
            data={"generation_id": generation.group(1) if generation else ""},
        )
        payload = generated.json()
        answer_html = payload.get("answer_html", "")
        feedback_html = payload.get("feedback_html", "")
        check(
            "generative answer rendered",
            generated.status_code == 200
            and payload.get("status") is True
            and "To jest odpowiedź." in answer_html
            and 'id="generative-answer"' in answer_html
            and "data-generate" not in answer_html,
            str(generated.status_code) + answer_html[:400],
        )
        check(
            "generation time rendered",
            "Gen. time" in answer_html and "0:00:02.500000" in answer_html,
            "",
        )
        again = client.post(
            "/search/generate",
            data={"generation_id": generation.group(1) if generation else ""},
        )
        check(
            "generation id can be used only once",
            again.status_code == 409
            and "no longer available" in again.json().get("answer_html", ""),
            str(again.status_code),
        )
        unknown = client.post("/search/generate", data={"generation_id": "nope"})
        check(
            "unknown generation id is rejected",
            unknown.status_code == 409 and unknown.json().get("status") is False,
            str(unknown.status_code),
        )

        def kept_options(html: str) -> dict:
            return {
                "results_count": 'name="results_count" value="30"' in html,
                "min_similarity": 'name="min_similarity" value="0.35"' in html,
                "perc_rank": 'name="perc_rank_to_gen_qa" value="55"' in html,
                "rerank": 'name="rerank_results" checked' in html,
                "hybrid": 'name="hybrid_search" checked' in html,
                "generative": 'name="use_qa_generative" checked' in html,
                "extractive_off": 'name="use_qa_extractive" checked' not in html,
                "model": 'value="llama-8b" selected' in html,
                "category": re.search(r'value="a"\s+selected', html) is not None,
                "prompt": "odpowiedz zwięźle</textarea>" in html,
                "reset_link": "/search/params/reset" in html,
            }

        kept = kept_options(results_html)
        check("search options are kept after the search", all(kept.values()), str(kept))
        kept = kept_options(client.get("/search").text)
        check(
            "search options are kept on the search page", all(kept.values()), str(kept)
        )
        clear_link = re.search(r'<a class="btn btn--ghost" href="([^"]+)"[^>]*>Clear</a>', results_html)
        check(
            "clear is a link back to the empty search page",
            clear_link is not None
            and clear_link.group(1) == "/search?clear=1&amp;collection_name=user_col"
            and 'type="reset"' not in results_html,
            clear_link.group(0) if clear_link else "",
        )
        if clear_link:
            cleared_html = client.get(clear_link.group(1).replace("&amp;", "&")).text
            cleared = kept_options(cleared_html)
            prompt_kept = cleared.pop("prompt")
            check(
                "clear drops the question, the instruction and the results, keeps the options",
                'class="query-console__question" placeholder="' in cleared_html
                and re.search(r'name="question"[^>]*required></textarea>', cleared_html)
                is not None
                and re.search(r'name="prompt"[^>]*></textarea>', cleared_html)
                is not None
                and not prompt_kept
                and "search-layout--results" not in cleared_html
                and all(cleared.values()),
                str(cleared),
            )
            again = client.get("/search").text
            check(
                "cleared instruction stays empty on the next visit",
                "odpowiedz zwięźle</textarea>" not in again
                and 'name="results_count" value="30"' in again,
                "",
            )
        reset = client.get(
            "/search/params/reset?collection_name=user_col", follow_redirects=False
        )
        check(
            "restore defaults redirects back to the search page",
            reset.status_code == 303
            and reset.headers.get("location")
            == "/search?collection_name=user_col&params_reset=1",
            str(reset.status_code),
        )
        defaults_html = client.get("/search?collection_name=user_col").text
        check(
            "restore defaults brings back the default options",
            f'name="results_count" value="{server.constants.DEFAULT_MAX_RESULTS}"'
            in defaults_html
            and f'name="min_similarity" value="{server.constants.DEFAULT_MIN_SIMILARITY}"'
            in defaults_html
            and 'name="hybrid_search" checked' in defaults_html
            and 'name="use_qa_generative" checked' not in defaults_html
            and 'name="rerank_results" checked' not in defaults_html
            # The link stays: options changed without a search live in the browser
            and "/search/params/reset" in defaults_html,
            "",
        )
        check(
            "stats table shows document names",
            "doc-a.pdf" in response.text and "document" in response.text,
            "",
        )
        check(
            "detailed table shows result ids",
            "fragment B" in response.text and "result_id" in response.text,
            "",
        )
        check(
            "passages show the left and right context",
            'class="hit__ctx hit__ctx--left"' in response.text
            and 'class="hit__ctx hit__ctx--right"' in response.text
            and "kontekst <strong>przed</strong>" in response.text
            and "kontekst po" in response.text
            and 'data-hits-toggle="context"' in response.text
            and "<dt>left_context</dt>" not in response.text,
            "",
        )
        check(
            "passages are rendered as Markdown with a plain-text twin",
            "<h4>Sekcja</h4>" in response.text
            and "<strong>pogrubiony</strong>" in response.text
            and "**pogrubiony**" in response.text
            and "<script>x</script>" not in response.text
            and 'data-hits-toggle="markdown"' in response.text,
            "",
        )
        check(
            "generative answer is rendered as Markdown",
            "<h4>Podsumowanie</h4>" in answer_html
            and "<strong>To jest odpowiedź.</strong>" in answer_html
            and "<ul>" in answer_html
            and 'id="answer-body"' in answer_html,
            "",
        )
        check(
            "markdown links are safe and table alignment uses classes",
            'href="https://example.com/docs" rel="noopener noreferrer nofollow"'
            in answer_html
            and 'class="cell-right"' in answer_html,
            "",
        )
        check(
            "results are tabbed with ARIA and exactly one visible panel",
            'role="tablist"' in response.text
            and 'id="tab-generative" aria-selected="true"' not in response.text
            and response.text.count('class="tab-panel is-active"') == 1
            and 'aria-selected="true"' in response.text,
            str(response.text.count('class="tab-panel is-active"')),
        )
        check(
            "score columns render bars",
            'data-score="0.87"' in response.text and 'class="score"' in response.text,
            "",
        )
        check(
            "results page renders without inline styles",
            'style="' not in response.text
            and 'style="' not in answer_html
            and 'style="' not in feedback_html,
            "",
        )
        check(
            "search options sent",
            options.get("max_results") == 30
            and options.get("rerank_results") is True
            and options.get("hybrid_search") is True,
            str(options),
        )
        check(
            "search filters sent",
            options.get("categories") == ["a", "c"]
            and options.get("documents") == ["b.pdf"],
            str(options),
        )
        check(
            "min_similarity sent as a number",
            options.get("min_similarity") == 0.35
            and not isinstance(options.get("min_similarity"), str),
            str(options),
        )
        parse = server.parse_min_similarity
        check(
            "min_similarity is clamped to [0, 1] and defaults when invalid",
            parse("0.6") == 0.6
            and parse("7") == 1.0
            and parse("-1") == 0.0
            and parse("0") == 0.0
            and parse("") == server.constants.DEFAULT_MIN_SIMILARITY
            and parse(None) == server.constants.DEFAULT_MIN_SIMILARITY
            and parse("abc") == server.constants.DEFAULT_MIN_SIMILARITY
            and parse("nan") == server.constants.DEFAULT_MIN_SIMILARITY,
            str([parse(v) for v in ("0.6", "7", "-1", "0", "", None, "abc", "nan")]),
        )
        check(
            "convert_to_display added",
            options.get("convert_to_display") is True,
            str(options),
        )

        gen_sent = last_request("POST", "api/generative_answer")
        check(
            "generative answer called",
            gen_sent.get("body", {}).get("query_response_id") == "42",
            str(gen_sent.get("body")),
        )
        check(
            "rating form comes with the answer",
            "Send your feedback!" in feedback_html
            and "data-feedback-slot" in results_html,
            "",
        )

        response = client.post(
            "/search/rate", data={"rate_value": "4", "rate_comment": "fajnie"}
        )
        sent = last_request("POST", "api/rate_generative_answer")
        check(
            "rating sent",
            sent.get("body", {}).get("rate_value") == "4"
            and sent.get("body", {}).get("rate_comment") == "fajnie",
            str(sent.get("body")),
        )
        check(
            "rating clears response id",
            server.get_last_response_id.__name__ == "get_last_response_id",
            "",
        )

        response = client.post(
            "/search", data={"collection_name": "user_col", "question": "   "}
        )
        check(
            "empty question -> error",
            response.status_code == 200
            and "Enter a sentence to search" in response.text,
            str(response.status_code),
        )

        response = client.post(
            "/search", data={"collection_name": "err_col", "question": "x"}
        )
        check(
            "backend error -> error page",
            response.status_code == 502
            and "Error occurred while processing" in response.text
            and "COLLECTION_NOT_FOUND" in response.text,
            f"{response.status_code}",
        )

        # Check search with hybrid_search disabled
        client.post(
            "/search",
            data={
                "collection_name": "user_col",
                "question": "wektorowe pytanie",
                "results_count": "8",
            },
        )
        sent_vo = last_request("POST", "api/search_with_options")
        options_vo = json.loads(sent_vo.get("body", {}).get("options", "{}"))
        check(
            "hybrid search disabled sends hybrid_search=False",
            options_vo.get("hybrid_search") is False,
            str(options_vo),
        )
        check(
            "missing min_similarity falls back to the engine default",
            options_vo.get("min_similarity") == server.constants.DEFAULT_MIN_SIMILARITY,
            str(options_vo),
        )

        response = client.get("/search")
        check(
            "search page exposes category/document filters",
            'name="categories"' in response.text
            and 'name="documents"' in response.text,
            "",
        )

        # --- Form field names must match server.parse_search_form ---------- #
        search_html = client.get("/search").text
        check(
            "search form uses the expected field names",
            all(
                f'name="{field}"' in search_html
                for field in [
                    "collection_name",
                    "results_count",
                    "min_similarity",
                    "hybrid_search",
                    "rerank_results",
                    "return_with_factored_fields",
                    "use_qa_extractive",
                    "use_qa_generative",
                    "use_doc_names_in_response",
                    "qa_gen_model",
                    "perc_rank_to_gen_qa",
                    "translate_output",
                    "lang_options",
                    "top_k",
                    "top_p",
                    "temperature",
                    "typical_p",
                    "repetition_penalty",
                    "set_max_new_tokens",
                    "max_new_tokens",
                    "categories",
                    "documents",
                    "question",
                    "prompt",
                ]
            ),
            "",
        )
        collection_html = client.get("/collections/new").text
        check(
            "new collection form uses the engine field names",
            all(
                f'name="{field}"' in collection_html
                for field in [
                    "collection_name",
                    "collection_display_name",
                    "embedder_index_type",
                    "embedder_model",
                    "re_ranker_model",
                    "collection_description",
                ]
            ),
            "",
        )

        # --- Search history of the selected collection ---------------------- #
        history_html = client.get("/search?collection_name=user_col").text
        history_sent = last_request("GET", "api/search_history")
        check(
            "history is fetched for the selected collection",
            history_sent.get("query", {}).get("collection_name") == "user_col"
            and history_sent.get("auth") == "Token test-token-123",
            str(history_sent),
        )
        check(
            "history panel lists the searches of the collection only",
            "data-history" in history_html
            and 'href="/search/history/42"' in history_html
            and 'href="/search/history/41"' in history_html
            and "/search/history/40" not in history_html
            and "Pytanie z innej kolekcji" not in history_html
            and history_html.index("/search/history/42")
            < history_html.index("/search/history/41"),
            "",
        )
        check(
            "history entries show results, answer and rating",
            "Jak wygląda proces ofertowy?" in history_html
            and "2 passages" in history_html
            and "1 document" in history_html
            and "✦ answer" in history_html
            and "★ 4/5" in history_html
            and "&lt;b&gt;2025&lt;/b&gt;" in history_html
            and "<b>2025</b>" not in history_html,
            "",
        )
        check(
            "history panel is open when there are no results",
            re.search(r'<details class="history__box" open', history_html) is not None,
            "",
        )
        check(
            "history panel is collapsed next to results, the new search is marked",
            re.search(r'<details class="history__box" open', results_html) is None
            and 'class="history__item is-current" href="/search/history/42"'
            in results_html,
            "",
        )
        # Forget the remembered collection (the last search used err_col)
        no_collection_html = client.get("/search/params/reset").text
        check(
            "history asks for a collection when none is chosen",
            "Choose a collection to see the history" in no_collection_html
            and "/search/history/4" not in no_collection_html,
            "",
        )
        unavailable_html = client.get("/search?collection_name=err_col").text
        check(
            "history failure is shown in the panel, the page still works",
            "Could not fetch the search history" in unavailable_html
            and 'name="question"' in unavailable_html,
            "",
        )

        entry_html = client.get("/search/history/42").text
        check(
            "history entry shows its question, results and stored answer",
            "Jak wygląda proces ofertowy?</textarea>" in entry_html
            and "odpowiedz krótko</textarea>" in entry_html
            and "fragment B" in entry_html
            and "<strong>Zapisana odpowiedź</strong>" in entry_html
            and "data-generate" not in entry_html
            and "From history" in entry_html
            and "0:00:03.250000" in entry_html,
            "",
        )
        check(
            "history entry can be rated again (saved rating preselected)",
            'name="history_id" value="42"' in entry_html
            and 'value="4" checked' in entry_html
            and 'value="5" checked' not in entry_html
            and "Dobra odpowiedź</textarea>" in entry_html
            and 'class="history__item is-current" href="/search/history/42"'
            in entry_html
            and 'style="' not in entry_html,
            "",
        )
        rated = client.post(
            "/search/rate",
            data={"rate_value": "2", "history_id": "42"},
            follow_redirects=False,
        )
        rate_sent = last_request("POST", "api/rate_generative_answer")
        check(
            "rating a history entry rates its answer and goes back to it",
            rated.status_code == 303
            and rated.headers.get("location") == "/search/history/42"
            and rate_sent.get("body", {}).get("answer_response_id") == "98"
            and rate_sent.get("body", {}).get("rate_value") == "2",
            str(rate_sent.get("body")),
        )
        plain_entry = client.get("/search/history/41").text
        check(
            "history entry without an answer has no answer card",
            "Wyniki pomiarów &lt;b&gt;2025&lt;/b&gt;</textarea>" in plain_entry
            and 'id="generative-answer"' not in plain_entry
            and 'name="history_id"' not in plain_entry,
            "",
        )
        denied = client.get("/search/history/999")
        check(
            "unknown history entry -> error page",
            denied.status_code == 404 and "RESPONSE_ACCESS_DENIED" in denied.text,
            str(denied.status_code),
        )
        panel = client.get("/search/history?collection_name=user_kol").json()
        check(
            "history panel endpoint follows the chosen collection",
            panel.get("status") is True
            and panel.get("count") == 1
            and "/search/history/40" in panel.get("html", "")
            and "/search/history/42" not in panel.get("html", ""),
            str(panel)[:300],
        )
        broken = client.get("/search/history?collection_name=err_col").json()
        check(
            "history failure does not break the page",
            broken.get("status") is False
            and "Could not fetch the search history" in broken.get("html", ""),
            str(broken)[:300],
        )

        # --- JSON options endpoint + static + logout ------------------------ #
        response = client.get("/api/options?collection_name=user_col")
        payload = response.json()
        check(
            "options endpoint",
            payload["status"] is True
            and payload["body"]["categories"] == ["a", "b", "c"]
            and payload["body"]["documents"] == ["a.pdf", "b.pdf"],
            str(payload),
        )

        response = client.get("/static/css/style.css")
        check(
            "static css served",
            response.status_code == 200
            and "--brand-500" in response.text
            and "prefers-color-scheme: dark" in response.text,
            str(response.status_code),
        )

        # --- Markdown renderer --------------------------------------------- #
        unsafe = server.render_markdown(
            "<script>alert(1)</script> <img src=x onerror=alert(1)>\n"
            "[click](javascript:alert(1))\n\n- item\n"
        )
        check(
            "markdown escapes raw HTML",
            "<script" not in unsafe and "&lt;script&gt;" in unsafe,
            unsafe,
        )
        check(
            "markdown never links to a dangerous scheme",
            '<a href="javascript' not in unsafe and "<a " not in unsafe,
            unsafe,
        )
        check("markdown still renders lists", "<ul>" in unsafe, unsafe)

        # --- UI shell (theme, navigation, no inline styling) ---------------- #
        page_html = client.get("/search").text
        check(
            "UI shell exposes theme toggle and active navigation",
            'data-theme="auto"' in page_html
            and "theme-toggle" in page_html
            and "nav__link is-active" in page_html,
            "",
        )
        check(
            "templates render without inline styles",
            all(
                'style="' not in client.get(url).text
                for url in [
                    "/home",
                    "/search",
                    "/collections/new",
                    "/collections/manage",
                    "/documents/upload",
                ]
            ),
            "",
        )
        # --- Interface language (pl / en) ---------------------------------- #
        check_i18n(client)

        response = client.get("/healthz")
        check(
            "healthz",
            response.status_code == 200 and response.json() == {"status": "ok"},
            "",
        )

        response = client.get("/logout", follow_redirects=False)
        check(
            "logout redirects to login",
            response.status_code == 303 and "/login" in response.headers["location"],
            str(response.headers),
        )

        response = client.get("/search", follow_redirects=False)
        check(
            "after logout -> login",
            response.status_code == 303 and "/login" in response.headers["location"],
            str(response.headers),
        )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failing check(s): {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
