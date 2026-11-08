"""A mock of the semantic-search-engine backend for development and contract tests.

Reproduces the paths, the `{status, body}` envelope and the response shapes from commit 58c0b8d
for the endpoints the frontend uses. The document contents are fictitious. All requests land
in `REQUEST_LOG`.

Run: uvicorn tests.mock_backend.server:app --port 8271 (from the ui_lite directory)
Login: any username, password "demo".
"""

from __future__ import annotations

import itertools
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock semantic-search-engine")
REQUEST_LOG: list[dict[str, Any]] = []
TOKEN = "mock-token"
_ids = itertools.count(100)

RAD = "Raport – Analiza związku Aktu w sprawie AI z prawem krajowym.pdf"
PRZ = "Przewodnik po AI dla administracji publicznej.pdf"
ZAS = "Zasady informowania o wykorzystaniu systemów AI.pdf"

COLLECTIONS = [
    {
        "id": 1,
        "name": "regulacje_ai",
        "display_name": "Regulacje AI",
        "description": "Ustawy, przewodniki i raporty o AI w administracji",
        "created_on": "2026-10-01T10:00:00Z",
        "metadata_json": None,
        "document_count": 6,
        "active_document_count": 6,
    },
    {
        "id": 2,
        "name": "polityki_hr",
        "display_name": "Polityki HR",
        "description": "Regulaminy i procedury kadrowe",
        "created_on": "2026-10-02T10:00:00Z",
        "metadata_json": None,
        "document_count": 3,
        "active_document_count": 3,
    },
]
DOCUMENTS = {
    "regulacje_ai": [
        "Akt w sprawie sztucznej inteligencji.pdf",
        PRZ,
        RAD,
        "Słownik pojęć AI.md",
        "Wytyczne zakupowe dla systemów AI.docx",
        ZAS,
    ],
    "polityki_hr": [
        "Regulamin pracy.pdf",
        "Regulamin pracy zdalnej.docx",
        "Procedura delegacji zagranicznych.pdf",
    ],
}
PAGES = {
    RAD: {
        14: "Rozdział 2 omawia obowiązki podmiotów publicznych. Organy administracji, które wdrażają systemy AI, są traktowane jako podmioty stosujące.\nUrzędy przestrzegają zasady poufności informacji i danych uzyskanych podczas wykonywania swoich zadań, w tym danych osobowych i tajemnic przedsiębiorstwa.",
        39: "Państwa członkowskie ustanawiają przepisy dotyczące kar za naruszenia rozporządzenia. Kary administracyjne nakładane na organy publiczne mogą wynosić do 500 000 euro.",
        44: "Każde państwo członkowskie wyznacza co najmniej jeden organ notyfikujący. W Polsce rolę tę ma pełnić minister właściwy do spraw informatyzacji.",
    },
    PRZ: {
        26: "Przed wdrożeniem systemu AI urząd przeprowadza ocenę skutków dla praw podstawowych. Wyniki oceny urząd przekazuje organowi nadzoru rynku.",
        31: "Kontrola i audyt programów operacyjnych wykorzystujących AI obejmują przegląd dokumentacji technicznej. Audyt prowadzi się co najmniej raz w roku.",
    },
    ZAS: {
        5: "Osoba, która wchodzi w interakcję z systemem AI, musi zostać o tym poinformowana najpóźniej w momencie pierwszego kontaktu."
    },
}
TOTAL_PAGES = {RAD: 92, PRZ: 58, ZAS: 12}

RESULTS = [
    {
        "document_name": RAD,
        "page_number": 14,
        "text_str": "Urzędy przestrzegają zasady poufności informacji i danych uzyskanych podczas wykonywania swoich zadań",
        "left_context": "Organy administracji, które wdrażają systemy AI, są traktowane jako podmioty stosujące.",
        "right_context": "",
        "score": 0.031,
        "score_normalized": 0.94,
    },
    {
        "document_name": PRZ,
        "page_number": 26,
        "text_str": "Przed wdrożeniem systemu AI urząd przeprowadza ocenę skutków dla praw podstawowych.",
        "left_context": "",
        "right_context": "Wyniki oceny urząd przekazuje organowi nadzoru rynku.",
        "score": 0.029,
        "score_normalized": 0.88,
    },
    {
        "document_name": ZAS,
        "page_number": 5,
        "text_str": "Osoba, która wchodzi w interakcję z systemem AI, musi zostać o tym poinformowana",
        "left_context": "",
        "right_context": "",
        "score": 0.027,
        "score_normalized": 0.77,
    },
    {
        "document_name": PRZ,
        "page_number": 31,
        "text_str": "Kontrola i audyt programów operacyjnych wykorzystujących AI obejmują przegląd dokumentacji technicznej.",
        "left_context": "",
        "right_context": "Audyt prowadzi się co najmniej raz w roku.",
        "score": 0.025,
        "score_normalized": 0.72,
    },
    {
        "document_name": RAD,
        "page_number": 44,
        "text_str": "Każde państwo członkowskie wyznacza co najmniej jeden organ notyfikujący.",
        "left_context": "",
        "right_context": "",
        "score": 0.024,
        "score_normalized": 0.81,
    },
]
ANSWERS = {
    "bullets": (
        "Urzędy, które stosują systemy AI, mają przede wszystkim takie obowiązki:\n\n"
        f"- **Poufność danych.** Chronią informacje i dane uzyskane przy wykonywaniu zadań [{RAD}].\n"
        f"- **Ocena skutków.** Przed wdrożeniem oceniają wpływ systemu na prawa podstawowe [{PRZ}].\n"
        f"- **Informowanie ludzi.** Mówią wprost, że ktoś rozmawia z systemem AI [{ZAS}].\n"
        f"- **Kontrola i audyt.** Co najmniej raz w roku sprawdzają dokumentację [Przewodnik po AI dla administracji publicznej]."
    ),
    "table": (
        "| Obowiązek | Kiedy | Źródło |\n|---|---|---|\n"
        f"| Poufność danych | stale | [{RAD}] |\n"
        f"| Ocena skutków | przed wdrożeniem | [{PRZ}] |\n"
        f"| Informowanie, że rozmówcą jest AI | przy pierwszym kontakcie | [{ZAS}] |\n\n"
        "Urząd odpowiada za dane, ocenę skutków i przejrzystość."
    ),
    "brief": f"Urząd musi chronić dane przekazywane do AI [{RAD}], przed wdrożeniem ocenić skutki [{PRZ}] i informować ludzi, że rozmawiają z AI [{ZAS}].",
}
CHATS: dict[int, dict[str, Any]] = {}
REQUIRED_OPTIONS = (
    "generative_model",
    "percentage_rank_mass",
    "use_doc_names_in_response",
)


def ok(body: Any) -> JSONResponse:
    return JSONResponse({"status": True, "body": body})


def err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"status": False, "errors": [{"error_code": code, "message": message}]},
        status_code=status,
    )


async def log(request: Request) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if request.method == "POST":
        try:
            body = await request.json()
        except ValueError:
            body = {}
    entry = {
        "method": request.method,
        "path": request.url.path,
        "params": dict(request.query_params),
        "json": body,
        "auth": request.headers.get("authorization"),
    }
    REQUEST_LOG.append(entry)
    return entry


def authorized(entry: dict[str, Any]) -> bool:
    return entry["auth"] in (f"Token {TOKEN}", f"Bearer {TOKEN}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/api/healthz")
async def healthz(request: Request):
    await log(request)
    return {"healthy": True, "dependencies": {}}


@app.post("/api/login")
async def login(request: Request):
    e = await log(request)
    data = e["json"]
    if data.get("code"):
        return ok({"token": TOKEN, "refresh_token": "mock-refresh"})
    if data.get("username") and data.get("password") == "demo":
        return JSONResponse({"token": TOKEN})
    return JSONResponse({"detail": "Invalid credentials"}, status_code=401)


@app.post("/api/login_url")
async def login_url(request: Request):
    await log(request)
    return ok(
        {"login_url": "http://localhost:8000/login/callback?code=mock&state=mock"}
    )


@app.post("/api/refresh_token")
async def refresh_token(request: Request):
    await log(request)
    return ok({"token": TOKEN, "refresh_token": "mock-refresh"})


@app.post("/api/logout")
async def logout(request: Request):
    await log(request)
    return ok({})


@app.get("/api/collections")
async def collections(request: Request):
    e = await log(request)
    if not authorized(e):
        return err(401, "e__auth_401", "Unauthorized")
    return ok({"collections": COLLECTIONS})


@app.get("/api/documents")
async def documents(request: Request):
    e = await log(request)
    if not authorized(e):
        return err(401, "e__auth_401", "Unauthorized")
    name = e["params"].get("collection_name")
    if name not in DOCUMENTS:
        return err(200, "e__data_404", "Collection not found")
    return ok(
        {
            "documents": [
                n if isinstance(n, dict) else {"name": n} for n in DOCUMENTS[name]
            ]
        }
    )


@app.get("/api/document_content")
async def document_content(request: Request):
    e = await log(request)
    if not authorized(e):
        return err(401, "e__auth_401", "Unauthorized")
    p = e["params"]
    name = p.get("document_name")
    if name not in DOCUMENTS.get(p.get("collection_name"), []):
        return err(200, "e__data_405", "Document not found")
    total = TOTAL_PAGES.get(name, 4)
    start, size = int(p.get("from_page") or 1), int(p.get("max_pages") or 200)
    numbers = list(range(start, min(total, start + size - 1) + 1))
    pages = [
        {
            "page": n,
            "content": PAGES.get(name, {}).get(n, f"{name} – treść strony {n}."),
            "chunks": 1,
        }
        for n in numbers
    ]
    truncated = numbers[-1] < total if numbers else False
    return ok(
        {
            "document_id": 1,
            "document_name": name,
            "pages": pages,
            "content": "\n\n".join(x["content"] for x in pages),
            "from_page": start,
            "total_pages": total,
            "truncated": truncated,
            "next_page": numbers[-1] + 1 if truncated else None,
        }
    )


@app.get("/api/generative_models")
async def generative_models(request: Request):
    e = await log(request)
    if not authorized(e):
        return err(401, "e__auth_401", "Unauthorized")
    return ok({"mock/bielik-11b": {"host": "http://llm"}})


@app.post("/api/new_chat")
async def new_chat(request: Request):
    e = await log(request)
    if not authorized(e):
        return err(401, "e__auth_401", "Unauthorized")
    chat_id = next(_ids)
    CHATS[chat_id] = {"collection": e["json"].get("collection_name"), "messages": []}
    return ok(
        {
            "chat": {
                "id": chat_id,
                "organisation_user": 1,
                "collection": 1,
                "created_at": now(),
                "options": e["json"].get("options"),
            }
        }
    )


def _message(chat_id: int, role: str, text: str) -> dict[str, Any]:
    msgs = CHATS[chat_id]["messages"]
    m = {
        "id": next(_ids),
        "chat": chat_id,
        "role": role,
        "text": text,
        "text_translated": None,
        "number": len(msgs) + 1,
        "date_time": now(),
        "generation_time": None,
    }
    msgs.append(m)
    return m


@app.post("/api/add_user_message")
async def add_user_message(request: Request):
    e = await log(request)
    if not authorized(e):
        return err(401, "e__auth_401", "Unauthorized")
    data = e["json"]
    chat_id = data.get("chat_id")
    if chat_id not in CHATS:
        return err(200, "e__chat_404", "Chat not found")
    options = data.get("options") or {}
    if any(k not in options for k in REQUIRED_OPTIONS):
        return JSONResponse({"detail": "KeyError"}, status_code=500)
    question = data.get("user_message", "")
    _message(chat_id, "user", question)
    allowed = (data.get("search_options") or {}).get("documents")
    results = (
        []
        if any(k in question.lower() for k in ("licencj", "licence"))
        else [r for r in RESULTS if not allowed or r["document_name"] in allowed]
    )
    prompt = (data.get("system_prompt") or "").lower()
    fmt = (
        "table"
        if "markdown table" in prompt
        else "brief" if "answer briefly" in prompt else "bullets"
    )
    if results:
        text = ANSWERS[fmt]
        state = [
            {
                "id": next(_ids),
                "content_supervisor_state": None,
                "rag_message_state": {
                    "id": next(_ids),
                    "sse_response": {
                        "id": next(_ids),
                        "detailed_results_json": {
                            str(i): r for i, r in enumerate(results)
                        },
                        "general_stats_json": {
                            r["document_name"]: {} for r in results
                        },
                    },
                    "sse_answer": {"id": next(_ids), "generated_answer": text},
                },
            }
        ]
    else:
        text = (
            "Ceny licencji zależą zwykle od liczby użytkowników i zakresu wdrożenia."
        )
        state = None
    _message(chat_id, "assistant", text)
    return ok(
        {
            "generation_time": 12.4,
            "history": CHATS[chat_id]["messages"],
            "last_state": state,
            "generated_assistant_message": text,
        }
    )


@app.get("/api/chats")
async def chats(request: Request):
    e = await log(request)
    if not authorized(e):
        return err(401, "e__auth_401", "Unauthorized")
    return ok(
        {
            "history": [
                {
                    "chat_id": cid,
                    "is_read_only": False,
                    "chat_history": c["messages"],
                }
                for cid, c in CHATS.items()
            ]
        }
    )


@app.post("/api/rate_generative_answer")
async def rate(request: Request):
    e = await log(request)
    if not authorized(e):
        return err(401, "e__auth_401", "Unauthorized")
    d = e["json"]
    if any(
        k not in d for k in ("answer_response_id", "rate_value", "rate_value_max")
    ):
        return err(400, "e__data_501", "Missing required parameters")
    return ok({})
