"""Contract tests: every frontend route calls the right backend endpoint with the right fields."""

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import calls

REQUIRED = {
    "generative_model",
    "percentage_rank_mass",
    "use_doc_names_in_response",
    "use_rag_supervisor",
    "user_msg_is_rag_question",
}


def test_app_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/ui-api/collections").status_code == 401


def test_login_wrong_password(client, backend_log):
    r = client.post("/login", data={"username": "anna", "password": "zle"})
    assert (
        r.status_code == 401 and "notice-error" in r.text
    )  # locale-independent: the login error is rendered
    assert calls(backend_log, "login")[0]["json"]["username"] == "anna"


def test_login_and_app_page(logged):
    r = logged.get("/")
    assert (
        r.status_code == 200
        and 'id="app-data"' in r.text
        and "/static/js/app.js" in r.text
    )


def test_collections_use_token_and_lang(logged, backend_log):
    r = logged.get("/ui-api/collections")
    c = r.json()["collections"][0]
    assert c == {
        "name": "regulacje_ai",
        "display_name": "Regulacje AI",
        "description": "Ustawy, przewodniki i raporty o AI w administracji",
        "document_count": 6,
        "active_document_count": 6,
    }
    e = calls(backend_log, "collections")[0]
    assert e["auth"] == "Token mock-token" and e["params"]["lang"] == "pl"


def test_documents_list(logged, backend_log):
    docs = logged.get(
        "/ui-api/documents", params={"collection": "regulacje_ai"}
    ).json()["documents"]
    assert docs[0] == {
        "name": "Akt w sprawie sztucznej inteligencji.pdf",
        "stem": "Akt w sprawie sztucznej inteligencji",
        "filetype": "PDF",
    }
    assert (
        calls(backend_log, "documents")[0]["params"]["collection_name"]
        == "regulacje_ai"
    )


def test_first_question_creates_chat_and_sends_required_options(logged, backend_log):
    r = logged.post(
        "/ui-api/ask",
        json={
            "question": "What obligations?",
            "collection": "regulacje_ai",
            "format": "table",
        },
    )
    assert r.status_code == 200
    data = r.json()
    new = calls(backend_log, "new_chat")[0]["json"]
    add = calls(backend_log, "add_user_message")[0]["json"]
    assert new["collection_name"] == "regulacje_ai" and REQUIRED <= set(
        new["options"]
    )
    assert (
        add["chat_id"] == data["chat_id"]
        and add["user_message"] == "What obligations?"
    )
    assert (
        REQUIRED <= set(add["options"])
        and add["options"]["generative_model"] == "mock/bielik-11b"
    )
    assert add["options"]["max_new_tokens"] == 900
    assert (
        "markdown table" in add["system_prompt"].lower()
        and "square brackets" in add["system_prompt"]
    )
    assert "documents" not in add["search_options"]
    a = data["answer"]
    assert not a["no_sources"] and a["answer_id"] and a["format"] == "table"
    assert "<table>" in a["html"] and 'class="fn approx"' in a["html"]
    assert {g["name"] for g in a["groups"]} >= {
        "Przewodnik po AI dla administracji publicznej.pdf"
    }  # mock backend data


def test_follow_up_reuses_chat(logged, backend_log):
    first = logged.post(
        "/ui-api/ask", json={"question": "Question 1", "collection": "regulacje_ai"}
    ).json()
    logged.post(
        "/ui-api/ask",
        json={
            "question": "Question 2",
            "collection": "regulacje_ai",
            "chat_id": first["chat_id"],
        },
    )
    assert len(calls(backend_log, "new_chat")) == 1
    assert [
        c["json"]["chat_id"] for c in calls(backend_log, "add_user_message")
    ] == [first["chat_id"]] * 2


def test_selected_documents_limit_search(logged, backend_log):
    doc = "Zasady informowania o wykorzystaniu systemów AI.pdf"  # mock backend document name
    a = logged.post(
        "/ui-api/ask",
        json={"question": "Q", "collection": "regulacje_ai", "documents": [doc]},
    ).json()["answer"]
    assert calls(backend_log, "add_user_message")[0]["json"]["search_options"][
        "documents"
    ] == [doc]
    assert [g["name"] for g in a["groups"]] == [doc] and a["scope_count"] == 1


def test_empty_selection_is_rejected_without_backend_call(logged, backend_log):
    r = logged.post(
        "/ui-api/ask",
        json={"question": "Q", "collection": "regulacje_ai", "documents": []},
    )
    assert r.status_code == 400 and not calls(backend_log, "add_user_message")


def test_no_sources_answer(logged):
    a = logged.post(
        "/ui-api/ask",
        json={
            "question": "How much does a licence cost?",
            "collection": "regulacje_ai",
        },
    ).json()["answer"]
    assert a["no_sources"] and a["groups"] == [] and a["answer_id"] is None


def test_history_and_resume_keep_sources_in_session(logged):
    chat = logged.post(
        "/ui-api/ask",
        json={"question": "What AI Act obligations?", "collection": "regulacje_ai"},
    ).json()
    chats = logged.get("/ui-api/chats").json()["chats"]
    assert (
        chats[0]["chat_id"] == chat["chat_id"]
        and chats[0]["title"] == "What AI Act obligations?"
        and chats[0]["collection"] == "regulacje_ai"
    )
    detail = logged.get(f"/ui-api/chats/{chat['chat_id']}").json()
    assert detail["collection"] == "regulacje_ai"
    assert detail["messages"][1]["answer"]["groups"]


def test_resume_after_new_session_has_no_sources(settings, backend_log):
    from tests.mock_backend import server as mock

    # Two separate frontend processes (e.g. a restart): session memory does not carry over, the backend returns only messages.
    with TestClient(
        create_app(settings, transport=httpx.ASGITransport(app=mock.app))
    ) as c1:
        c1.post("/login", data={"username": "a", "password": "demo"})
        chat_id = c1.post(
            "/ui-api/ask",
            json={"question": "What obligations?", "collection": "regulacje_ai"},
        ).json()["chat_id"]
    with TestClient(
        create_app(settings, transport=httpx.ASGITransport(app=mock.app))
    ) as c2:
        c2.post("/login", data={"username": "a", "password": "demo"})
        detail = c2.get(f"/ui-api/chats/{chat_id}").json()
    assert detail["collection"] is None and detail["messages"][1]["legacy"] is True


def test_rate_sends_answer_id_and_scale(logged, backend_log):
    a = logged.post(
        "/ui-api/ask", json={"question": "Q", "collection": "regulacje_ai"}
    ).json()["answer"]
    r = logged.post(
        "/ui-api/rate",
        json={"answer_id": a["answer_id"], "value": 0, "comment": "Wrong page"},
    )
    assert r.status_code == 200
    sent = calls(backend_log, "rate_generative_answer")[0]["json"]
    assert (
        sent["answer_response_id"],
        sent["rate_value"],
        sent["rate_value_max"],
        sent["rate_comment"],
    ) == (a["answer_id"], 0, 1, "Wrong page")


def test_document_preview_params_and_paging(logged, backend_log):
    name = "Raport – Analiza związku Aktu w sprawie AI z prawem krajowym.pdf"  # mock backend document name
    d = logged.get(
        "/ui-api/document",
        params={"collection": "regulacje_ai", "name": name, "from_page": 14},
    ).json()
    p = calls(backend_log, "document_content")[0]["params"]
    assert (
        p["document_name"] == name
        and p["from_page"] == "14"
        and p["max_pages"] == "3"
    )
    assert (
        [x["page"] for x in d["pages"]] == [14, 15, 16]
        and d["next_page"] == 17
        and d["total_pages"] == 92
    )


def test_missing_document_maps_to_backend_error(logged):
    r = logged.get(
        "/ui-api/document", params={"collection": "regulacje_ai", "name": "Brak.pdf"}
    )
    assert r.status_code == 502 and r.json()["message"] == "Document not found"


def test_backend_down_gives_503(settings):
    def down(request):
        raise httpx.ConnectError("down")

    app = create_app(settings, transport=httpx.MockTransport(down))
    with TestClient(app) as c:
        r = c.post("/login", data={"username": "a", "password": "demo"})
        assert r.status_code == 503 and "notice-error" in r.text
        assert c.get("/ui-api/health").status_code == 503


def test_language_switch_changes_lang_param(logged, backend_log):
    logged.get("/lang/en", follow_redirects=False)
    logged.get("/ui-api/collections")
    assert calls(backend_log, "collections")[-1]["params"]["lang"] == "en"
