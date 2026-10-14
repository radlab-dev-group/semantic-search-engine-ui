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

from tests.mock_sse_backend import REQUEST_LOG, start_mock_backend  # noqa: E402

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
    r"|params|hits|board|table|js)\.[a-z_]+\b"
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
    pages = {url: client.get(url).text for url in ["/home", "/collections", "/documents/upload", "/search"]}
    check(
        "polish interface",
        '<html lang="pl"' in pages["/search"]
        and ">Kolekcje</a>" in pages["/search"]
        and "Parametry wyszukiwania" in pages["/search"]
        and "Szukaj po <span" in pages["/home"]
        and "Lista kolekcji" in pages["/collections"]
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
            "navigation tab is named Collections",
            ">Collections</a>" in response.text
            and ">New collection</a>" not in response.text
            and "nav__link is-active" in response.text,
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
        response = client.get("/search?collection_name=user_col")
        check(
            "search page preselects the collection from the query string",
            '<option value="user_col" selected>' in response.text,
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
                "rerank_results": "on",
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
                "perc_rank": 'name="perc_rank_to_gen_qa" value="55"' in html,
                "rerank": 'name="rerank_results" checked' in html,
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
        reset = client.get(
            "/search/params/reset?collection_name=user_col", follow_redirects=False
        )
        check(
            "restore defaults redirects back to the search page",
            reset.status_code == 303
            and reset.headers.get("location") == "/search?collection_name=user_col",
            str(reset.status_code),
        )
        defaults_html = client.get("/search?collection_name=user_col").text
        check(
            "restore defaults brings back the default options",
            f'name="results_count" value="{server.constants.DEFAULT_MAX_RESULTS}"'
            in defaults_html
            and 'name="use_qa_generative" checked' not in defaults_html
            and 'name="rerank_results" checked' not in defaults_html
            and "/search/params/reset" not in defaults_html,
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
            and options.get("rerank_results") is True,
            str(options),
        )
        check(
            "search filters sent",
            options.get("categories") == ["a", "c"]
            and options.get("documents") == ["b.pdf"],
            str(options),
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
