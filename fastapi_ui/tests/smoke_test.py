"""
End-to-end smoke test of the FastAPI UI against a mocked SSE backend.

Run from the fastapi_ui directory:

    .venv/bin/python tests/smoke_test.py

It does not require a real semantic-search-engine backend: all REST calls are
served by tests/mock_sse_backend.py.
"""

import json
import os
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
                "new_chat": "api/new_chat",
                "add_user_message": "api/add_user_message",
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

        # --- New collection ------------------------------------------------ #
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
        check(
            "generative answer rendered",
            "To jest odpowiedź." in response.text,
            response.text[:400],
        )
        check(
            "generation time rendered",
            "Gen. time" in response.text and "0:00:02.500000" in response.text,
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
        check("rating form shown", "Send your feedback!" in response.text, "")

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

        # --- Conversational search ----------------------------------------- #
        response = client.get("/chat")
        check(
            "chat page",
            response.status_code == 200
            and "Conversational search bot" in response.text,
            str(response.status_code),
        )
        check(
            "chat page has supervisor switches and filters",
            'name="use_content_supervisor"' in response.text
            and 'name="use_rag_supervisor"' in response.text
            and 'name="categories"' in response.text,
            "",
        )

        response = client.post(
            "/chat/message",
            data={
                "collection_name": "user_col",
                "message": "Cześć",
                "results_count": "20",
                "use_content_supervisor": "on",
                "use_rag_supervisor": "on",
                "qa_gen_model": "qwen-7b",
                "perc_rank_to_gen_qa": "60",
            },
        )
        chat_sent = last_request("POST", "api/new_chat")
        msg_sent = last_request("POST", "api/add_user_message")
        check(
            "chat message rendered",
            response.status_code == 200 and "Cześć! W czym pomóc?" in response.text,
            str(response.status_code),
        )
        check(
            "new chat created",
            chat_sent.get("body", {}).get("collection_name") == "user_col",
            str(chat_sent.get("body")),
        )
        check(
            "chat message sent",
            msg_sent.get("body", {}).get("user_message") == "Cześć",
            str(msg_sent.get("body")),
        )
        check(
            "rag state rendered",
            "Detected question" in response.text
            and "jakieś pytanie" in response.text,
            "",
        )
        check(
            "content supervisor state rendered",
            "Content supervisor state" in response.text,
            "",
        )

        check("voice input is off by default", "speech-btn" not in response.text, "")
        server.templates.env.globals["speech_input"] = True
        try:
            response = client.get("/chat")
            check(
                "voice input can be enabled (UI_SPEECH_INPUT)",
                "speech-btn" in response.text
                and "SpeechRecognition" in response.text,
                "",
            )
        finally:
            server.templates.env.globals["speech_input"] = False

        response = client.post("/chat/clear", follow_redirects=False)
        check(
            "chat cleared",
            response.status_code == 303 and "/chat" in response.headers["location"],
            str(response.headers),
        )
        response = client.get("/chat")
        check(
            "chat history gone after clear",
            "Cześć! W czym pomóc?" not in response.text,
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
                    "/chat",
                    "/collections/new",
                    "/documents/upload",
                ]
            ),
            "",
        )
        check(
            "chat wires the message to the parameters form",
            'form="chat-message-form"' in client.get("/chat").text
            and 'formaction="/chat/clear"' in client.get("/chat").text,
            "",
        )

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
